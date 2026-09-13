"""Cyclone observation repository — the only way the prediction service reads storm histories.

    Repository → Service (services/prediction_service.py) → Prediction pipeline (ml/prediction)

The model never touches storage. This implementation reads the IBTrACS-derived observation table
exported by prediction_model/scripts/export_backend_data.py (held-out test storms, so every forecast
served is out-of-sample). MongoDB's cyclone_database (app/db/mongo.py) now holds extracted cyclone
collections; a Mongo-backed repository only has to return the same validated DataFrames to replace this one.

Environment: CYCLONE_DATA_PATH (default backend/app/data/cyclones/observations.csv.gz).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ml.prediction.features import validate_observations

logger = logging.getLogger(__name__)
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "cyclones" / "observations.csv.gz"


@dataclass(frozen=True)
class StormSummary:
    storm_id: str
    name: str
    season: int
    basin: str
    region: str
    subregion: str
    area: str
    first_time: pd.Timestamp
    last_time: pd.Timestamp
    fixes: int
    peak_wind_kt: float | None
    split: str | None


class FileCycloneRepository:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.environ.get("CYCLONE_DATA_PATH") or DEFAULT_PATH)
        self._storms: dict[str, pd.DataFrame] = {}
        self._summaries: list[StormSummary] = []
        self._lock = threading.Lock()
        self.error: str | None = None
        self.validation: dict = {}

    @property
    def ready(self) -> bool:
        return bool(self._storms)

    def load(self) -> None:
        with self._lock:
            try:
                raw = pd.read_csv(self.path, keep_default_na=False, na_values=[""], low_memory=False)
                clean, self.validation = validate_observations(raw)
            except Exception as exc:  # recorded, never raised: the rest of the API keeps working
                self.error = f"{type(exc).__name__}: {exc}"
                logger.exception("Could not load cyclone observations from %s", self.path)
                return
            storms, summaries = {}, []
            for storm_id, storm in clean.groupby("storm_id", sort=True):
                storm = storm.sort_values("time").reset_index(drop=True)
                storms[str(storm_id)] = storm
                first = storm.iloc[0]
                peak = storm["wind_kt"].max()
                summaries.append(StormSummary(
                    storm_id=str(storm_id), name=str(first.get("name", "")), season=int(first.get("season", 0) or 0),
                    basin=str(first.get("basin", "")), region=str(first.get("region", "")), subregion=str(first.get("subregion", "")),
                    area=str(first.get("area", "")), first_time=storm["time"].iloc[0], last_time=storm["time"].iloc[-1],
                    fixes=len(storm), peak_wind_kt=None if pd.isna(peak) else float(peak),
                    split=str(first["split"]) if "split" in storm.columns else None,
                ))
            self._storms, self._summaries, self.error = storms, summaries, None
            logger.info("Cyclone observations loaded: %d storms, %d fixes from %s", len(storms), len(clean), self.path)

    def list_storms(self, region: str | None = None, subregion: str | None = None, basin: str | None = None) -> list[StormSummary]:
        out = self._summaries
        if region:
            out = [s for s in out if s.region == region]
        if subregion:
            out = [s for s in out if s.subregion == subregion]
        if basin:
            out = [s for s in out if s.basin == basin.upper()]
        return out

    def get_observations(self, storm_id: str) -> pd.DataFrame | None:
        """All fixes of one storm, validated and time-sorted (a copy the caller may modify)."""
        storm = self._storms.get(storm_id)
        return None if storm is None else storm.copy()

    def get_summary(self, storm_id: str) -> StormSummary | None:
        return next((s for s in self._summaries if s.storm_id == storm_id), None)


class RepositoryUnavailableError(RuntimeError):
    """The storage behind a repository cannot be reached (the service answers 503 DATABASE_UNAVAILABLE)."""


# IBTrACS basin (+ North Indian subbasin) → the UI (region, subregion, area) the held-out table uses.
_BASIN_AREAS = {
    "SI": ("south_indian_ocean", "", "south_indian_ocean"),
    "WP": ("pacific_ocean", "western_pacific", "western_pacific"),
    "EP": ("pacific_ocean", "eastern_pacific", "eastern_pacific"),
    "SP": ("pacific_ocean", "southern_pacific", "southern_pacific"),
}
_NI_SUBBASINS = {"BB": "bay_of_bengal", "AS": "arabian_sea"}


def _ui_area(basin: str, subbasin: str) -> tuple[str, str, str]:
    if basin == "NI":
        sub = _NI_SUBBASINS.get(subbasin, "")
        return "north_indian_ocean", sub, sub
    return _BASIN_AREAS.get(basin, ("", "", ""))


class MongoCycloneRepository:
    """Read-only view of MongoDB cyclone_database (cyclones + cyclone_positions), through app/db/mongo.py.

    The prediction service reads it for storms that are not in the held-out table. Its positions carry time,
    position, wind and pressure only: the inputs the model also needs (distance to land, storm nature) are left
    missing — never filled in — and no storm there has the 5-fix, 6-hourly window the model needs, so such storms
    get a truthful INSUFFICIENT_HISTORY / MISSING_FEATURES instead of a forecast from invented inputs. Its wind
    values also differ from the model's USA_WIND basis for some fixes. Nothing here writes to MongoDB.
    """

    @staticmethod
    def _handle():
        from app.db.mongo import mongodb  # lazy: the file repository works without MongoDB settings
        return mongodb.cyclone_db

    @property
    def connected(self) -> bool:
        return self._handle() is not None

    def status_detail(self) -> str:
        return "cyclone_database connected (read-only)" if self.connected else "Not connected (MONGODB_URI in backend/.env)"

    def get_observations(self, storm_id: str) -> pd.DataFrame | None:
        """All positions of one storm as a validated, time-sorted observation table; None if the storm is not there."""
        from pymongo.errors import PyMongoError

        db = self._handle()
        if db is None:
            raise RepositoryUnavailableError("cyclone_database is not connected")
        try:
            positions = list(db.cyclone_positions.find({"cyclone_id": storm_id}, {"_id": 0}))
            meta = (db.cyclones.find_one({"external_id": storm_id}, {"_id": 0}) or {}) if positions else {}
        except PyMongoError as exc:
            raise RepositoryUnavailableError(f"cyclone_database query failed: {exc}") from exc
        if not positions:
            return None
        basin = str(meta.get("basin") or "")
        region, subregion, area = _ui_area(basin, str(meta.get("subregion") or ""))
        rows = [{
            "storm_id": storm_id, "time": p.get("timestamp"), "lat": p.get("latitude"), "lon": p.get("longitude"),
            "wind_kt": p.get("wind_speed"), "pressure_hpa": p.get("pressure"),
            "nature": p.get("nature") or "", "dist2land_km": p.get("dist2land_km"),  # absent in the current collection
            "area": area, "region": region, "subregion": subregion, "basin": basin, "name": str(meta.get("name") or ""),
        } for p in positions]
        clean, _ = validate_observations(pd.DataFrame(rows))  # also drops the duplicated fixes the collection holds
        return clean if len(clean) else None


repository = FileCycloneRepository()
mongo_repository = MongoCycloneRepository()


def load_cyclone_data() -> None:
    repository.load()
