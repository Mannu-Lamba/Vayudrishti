"""Cyclone registry: the real storms and satellite frame records the console lists, read from MongoDB cyclone_database.

    Repository → Service (services/registry_service.py) → routers (cyclones, regions, events, satellite)

cyclone_database (the user's extraction) holds `cyclones` (every storm record is stored twice), `cyclone_positions`
(sparse fixes), `satellite_observations` and `classification_results`. Its 4,000 `SYS_…` records are class-0
(no-cyclone) GridSat-B1 samples, not storms: they are never listed as cyclones, only as satellite frames.

A storm whose complete best track the API already serves (the held-out IBTrACS table, repositories.cyclone_repository)
uses that track — it is also the only kind the prediction model can forecast. Every other storm uses its database fixes.
Read-only. The snapshot is rebuilt at most every REFRESH_SECONDS, so new extraction results appear without a restart.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import pandas as pd

from repositories import cyclone_repository
from repositories.cyclone_repository import RepositoryUnavailableError

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 300
DATABASE = "cyclone_database"
FIX_COLUMNS = ["time", "lat", "lon", "wind_kt", "pressure_hpa"]
BASIN_REGION = {"NI": "north_indian_ocean", "SI": "south_indian_ocean", "WP": "pacific_ocean", "EP": "pacific_ocean", "SP": "pacific_ocean"}
BASIN_AREA = {"SI": "south_indian_ocean", "WP": "western_pacific", "EP": "eastern_pacific", "SP": "southern_pacific"}
NI_SPLIT_LON = 77.5  # tip of the Indian peninsula: west = Arabian Sea, east = Bay of Bengal


def area_of(basin: str, subbasin: str, region_text: str, lon: float | None) -> tuple[str, str, str]:
    """(region id, subregion id, area) in the UI taxonomy the rest of the API uses."""
    region = BASIN_REGION.get(basin, "")
    if basin == "NI":
        if subbasin == "AS" or (subbasin != "BB" and "Arabian" in region_text):
            sub = "arabian_sea"
        elif subbasin == "BB" or "Bengal" in region_text:
            sub = "bay_of_bengal"
        else:
            sub = "arabian_sea" if lon is not None and lon < NI_SPLIT_LON else "bay_of_bengal"
        return region, sub, sub
    area = BASIN_AREA.get(basin, "")
    return region, "" if basin == "SI" else area, area


@dataclass
class RegistryStorm:
    storm_id: str
    name: str
    basin: str
    region_id: str
    subregion_id: str
    area: str
    fixes: pd.DataFrame  # FIX_COLUMNS, time-sorted, unique times
    source: str
    forecastable: bool  # the full best track is on the server, so the prediction model can run

    @property
    def first_time(self) -> pd.Timestamp:
        return self.fixes["time"].iloc[0]

    @property
    def last_time(self) -> pd.Timestamp:
        return self.fixes["time"].iloc[-1]

    @property
    def peak_wind_kt(self) -> float | None:
        peak = self.fixes["wind_kt"].max()
        return None if pd.isna(peak) else float(peak)


@dataclass
class FrameRecord:
    frame_id: str
    storm_id: str
    source: str | None
    channel: str | None
    time: pd.Timestamp
    latitude: float | None
    longitude: float | None
    image_url: str | None
    region_id: str
    subregion_id: str
    area: str
    label: int | None  # classification_results class: 1 = cyclone sample, 0 = no-cyclone sample


@dataclass
class RegistrySnapshot:
    storms: dict[str, RegistryStorm]
    frames: list[FrameRecord]
    built_at: float


class RegistryRepository:
    def __init__(self) -> None:
        self._snapshot: RegistrySnapshot | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> RegistrySnapshot:
        with self._lock:
            if self._snapshot is None or time.monotonic() - self._snapshot.built_at > REFRESH_SECONDS:
                try:
                    self._snapshot = self._build()
                except RepositoryUnavailableError:
                    if self._snapshot is None:
                        raise
                    logger.warning("cyclone_database unreachable; serving the registry snapshot from %.0f s ago",
                                   time.monotonic() - self._snapshot.built_at)
            return self._snapshot

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None

    @staticmethod
    def _database_fixes(positions: list[dict]) -> dict[str, pd.DataFrame]:
        if not positions:
            return {}
        pos = pd.DataFrame(positions)
        pos["time"] = pd.to_datetime(pos["timestamp"], utc=True, errors="coerce")
        pos = pos.dropna(subset=["time", "latitude", "longitude"])
        out = {}
        for storm_id, group in pos.groupby("cyclone_id"):
            fixes = pd.DataFrame({
                "time": group["time"], "lat": group["latitude"].astype(float), "lon": group["longitude"].astype(float),
                "wind_kt": pd.to_numeric(group.get("wind_speed"), errors="coerce"),
                "pressure_hpa": pd.to_numeric(group.get("pressure"), errors="coerce"),
            })
            out[str(storm_id)] = fixes.drop_duplicates("time").sort_values("time").reset_index(drop=True)  # the collection repeats fixes
        return out

    def _build(self) -> RegistrySnapshot:
        from pymongo.errors import PyMongoError

        from app.db.mongo import mongodb

        db = mongodb.cyclone_db
        if db is None:
            raise RepositoryUnavailableError("cyclone_database is not connected")
        try:
            records = list(db.cyclones.find({}, {"_id": 0}))
            positions = list(db.cyclone_positions.find({"cyclone_id": {"$not": {"$regex": "^SYS_"}}}, {"_id": 0}))
            observations = list(db.satellite_observations.find({}, {"cyclone_id": 1, "source": 1, "channel": 1, "timestamp": 1,
                                                                    "latitude": 1, "longitude": 1, "image_url": 1}))
            labels = {r.get("observation_id"): r.get("class") for r in db.classification_results.find({}, {"_id": 0, "observation_id": 1, "class": 1})}
        except PyMongoError as exc:
            raise RepositoryUnavailableError(f"cyclone_database query failed: {exc}") from exc

        held = cyclone_repository.repository
        meta: dict[str, dict] = {}
        for record in records:
            meta.setdefault(str(record.get("external_id")), record)  # each storm is stored twice
        database_fixes = self._database_fixes(positions)

        storms: dict[str, RegistryStorm] = {}
        for storm_id, record in meta.items():
            if storm_id.startswith("SYS_"):
                continue  # class-0 no-cyclone samples, not storms
            full = held.get_observations(storm_id) if held.ready else None
            if full is not None:
                fixes, source, forecastable = full[FIX_COLUMNS].reset_index(drop=True), f"{DATABASE} + held-out IBTrACS best track", True
            elif storm_id in database_fixes:
                fixes, source, forecastable = database_fixes[storm_id], DATABASE, False
            else:
                continue  # a record without a single position cannot be placed on the map
            basin = str(record.get("basin") or "")
            region, sub, area = area_of(basin, str(record.get("subregion") or ""), str(record.get("region") or ""), float(fixes["lon"].iloc[-1]))
            storms[storm_id] = RegistryStorm(storm_id, str(record.get("name") or ""), basin, region, sub, area, fixes, source, forecastable)
        if held.ready:  # held-out storms the API serves that the database does not hold (yet)
            for summary in held.list_storms():
                if summary.storm_id not in storms:
                    fixes = held.get_observations(summary.storm_id)[FIX_COLUMNS].reset_index(drop=True)
                    storms[summary.storm_id] = RegistryStorm(summary.storm_id, summary.name, summary.basin, summary.region, summary.subregion,
                                                             summary.area, fixes, "held-out IBTrACS best track", True)

        frames: list[FrameRecord] = []
        for obs in observations:
            stamp = pd.to_datetime(obs.get("timestamp"), utc=True, errors="coerce")
            if pd.isna(stamp):
                continue
            storm_id = str(obs.get("cyclone_id") or "")
            storm, record, lon = storms.get(storm_id), meta.get(storm_id, {}), obs.get("longitude")
            region, sub, area = ((storm.region_id, storm.subregion_id, storm.area) if storm else
                                 area_of(str(record.get("basin") or ""), str(record.get("subregion") or ""), str(record.get("region") or ""), lon))
            frames.append(FrameRecord(str(obs["_id"]), storm_id, obs.get("source"), obs.get("channel"), stamp, obs.get("latitude"), lon,
                                      obs.get("image_url"), region, sub, area, labels.get(obs["_id"])))
        frames.sort(key=lambda frame: frame.time)
        logger.info("Registry built from %s: %d storms (%d forecastable), %d satellite frame records", DATABASE, len(storms),
                    sum(s.forecastable for s in storms.values()), len(frames))
        return RegistrySnapshot(storms, frames, time.monotonic())


registry_repository = RegistryRepository()
