"""Registry service: real storms, regions, events and satellite frame records → API responses.

Routers call only this module; storage stays behind repositories.registry_repository. Nothing is invented: a value
the data does not hold is null, and an unreachable database is a 503 DATABASE_UNAVAILABLE, never demo data.
"""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ml.prediction.categories import imd_category
from ml.prediction.geo import KT_TO_KMH, bearing_deg, compass_point, haversine_km
from models.registry import (
    ArchivePage, ArchiveSummaryOut, CycloneOut, EventOut, HistoricalCycloneOut, HistoryPage, LocationOut, ObservedSystemOut,
    RegionalObservationOut, SeasonCount, TrackFixOut,
)
from repositories.cyclone_repository import RepositoryUnavailableError
from repositories.registry_repository import RegistryStorm, registry_repository
from services.errors import MlServiceError

logger = logging.getLogger(__name__)

REFERENCE = Path(__file__).resolve().parents[1] / "app" / "data" / "reference"
AREA_LABELS = {"arabian_sea": "Arabian Sea", "bay_of_bengal": "Bay of Bengal", "south_indian_ocean": "South Indian Ocean",
               "western_pacific": "Western Pacific", "eastern_pacific": "Eastern Pacific", "southern_pacific": "Southern Pacific"}
ACTIVE_WITHIN = pd.Timedelta(hours=24)
OBSERVATION_WINDOW = pd.Timedelta(hours=3)
DEFAULT_FRAMES = 24  # the satellite timeline shows the latest frames when no time range is asked for
GRIDSAT = "NOAA_GridSat_B1"
UNRECORDED = "unrecorded"
SOURCES = {
    GRIDSAT: {"id": GRIDSAT, "name": "GridSat-B1", "family": "GridSat", "agency": "NOAA NCEI", "dataProvider": "NOAA NCEI",
              "instrument": "ISCCP B1 geostationary imagers, merged on a global grid", "serviceSlot": None, "subSatelliteLongitude": None,
              "cadenceMinutes": 180, "channels": {"infrared": {"band": "IRWIN", "wavelengthUm": 11.0, "resolutionKm": 8.0}}},
    UNRECORDED: {"id": UNRECORDED, "name": "Source not recorded", "family": "—", "agency": "—", "dataProvider": None, "instrument": "—",
                 "serviceSlot": None, "subSatelliteLongitude": None, "cadenceMinutes": None, "channels": {}},
}
LABELS = {1: "cyclone (class 1)", 0: "no cyclone (class 0)"}


# ---------------------------------------------------------------- helpers

def iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value) -> float | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value) else float(value)


def _kmh(kt) -> float | None:
    kt = _num(kt)
    return None if kt is None else round(kt * KT_TO_KMH, 1)


def display_name(name: str) -> str:
    if not name or name.upper() in {"UNNAMED", "NOT_NAMED", "UNKNOWN"}:
        return "Unnamed"
    return "-".join(part.capitalize() for part in name.split("-"))


def _parse_time(value: str | None, field: str) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        raise MlServiceError("INVALID_TIME", f"`{field}` must be an ISO 8601 timestamp, e.g. 2020-05-18T18:00:00Z.", 400) from None
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _snapshot():
    try:
        return registry_repository.snapshot()
    except RepositoryUnavailableError as exc:
        logger.warning("Registry unavailable: %s", exc)
        raise MlServiceError("DATABASE_UNAVAILABLE", "The cyclone database is not reachable, so the cyclone registry cannot be read.", 503) from None


def _in_selection(storm_or_frame, region: str | None, subregion: str | None) -> bool:
    if region and storm_or_frame.region_id != region:
        return False
    return not subregion or storm_or_frame.subregion_id == subregion


def _page(items: list, page: int, page_size: int) -> tuple[list, int, int]:
    page, page_size = max(1, page), max(1, min(page_size, 1000))
    return items[(page - 1) * page_size: page * page_size], page, page_size


# ---------------------------------------------------------------- cyclones

def cyclone_out(storm: RegistryStorm, now: pd.Timestamp) -> CycloneOut:
    fixes = storm.fixes
    last = fixes.iloc[-1]
    direction, speed = None, None
    if len(fixes) >= 2:
        prev = fixes.iloc[-2]
        hours = (last["time"] - prev["time"]).total_seconds() / 3600
        if hours > 0:
            direction = compass_point(float(bearing_deg(prev["lat"], prev["lon"], last["lat"], last["lon"])))
            speed = round(float(haversine_km(prev["lat"], prev["lon"], last["lat"], last["lon"])) / hours, 1)
    label = AREA_LABELS.get(storm.area, "Indian Ocean" if storm.basin == "NI" else storm.basin)
    peak = storm.peak_wind_kt
    return CycloneOut(
        id=storm.storm_id, code=storm.storm_id, name=display_name(storm.name),
        status="active" if now - storm.last_time <= ACTIVE_WITHIN else "historical",
        category=imd_category(_num(last["wind_kt"])), region=label, basin=storm.basin,
        wind_kmh=_kmh(last["wind_kt"]), pressure_hpa=_num(last["pressure_hpa"]), movement_direction=direction, movement_speed_kmh=speed,
        location=LocationOut(latitude=float(last["lat"]), longitude=float(last["lon"]), label=label),
        observed_at=iso(storm.last_time), first_observed_at=iso(storm.first_time), season=int(storm.first_time.year), fixes=len(fixes),
        peak_wind_kmh=_kmh(peak), peak_category=imd_category(peak), source=storm.source, forecast_available=storm.forecastable,
    )


def list_cyclones(region, subregion, basin, start_date, end_date, active, limit) -> list[CycloneOut]:
    snap, now = _snapshot(), pd.Timestamp.now(tz="UTC")
    lo, hi = _parse_time(start_date, "startDate"), _parse_time(end_date, "endDate")
    storms = [s for s in snap.storms.values() if _in_selection(s, region, subregion) and (not basin or s.basin == basin.upper())
              and (lo is None or s.last_time >= lo) and (hi is None or s.last_time <= hi)]
    if active is not None:
        storms = [s for s in storms if (now - s.last_time <= ACTIVE_WITHIN) is active]
    storms.sort(key=lambda s: s.last_time, reverse=True)
    return [cyclone_out(s, now) for s in storms[:limit]]


def _storm(cyclone_id: str) -> RegistryStorm:
    storm = _snapshot().storms.get(cyclone_id)
    if storm is None:
        raise MlServiceError("CYCLONE_NOT_FOUND", "This cyclone is not in the registry.", 404)
    return storm


def get_cyclone(cyclone_id: str) -> CycloneOut:
    return cyclone_out(_storm(cyclone_id), pd.Timestamp.now(tz="UTC"))


def history(cyclone_id: str, page: int, page_size: int, start: str | None, end: str | None) -> HistoryPage:
    storm = _storm(cyclone_id)
    fixes = storm.fixes
    lo, hi = _parse_time(start, "start"), _parse_time(end, "end")
    if lo is not None:
        fixes = fixes[fixes["time"] >= lo]
    if hi is not None:
        fixes = fixes[fixes["time"] <= hi]
    anchor = storm.last_time
    items = []
    for row in fixes.itertuples():
        hours = round((row.time - anchor).total_seconds() / 3600, 1)
        items.append(TrackFixOut(id=f"{cyclone_id}-h-{iso(row.time)}", label="NOW" if hours == 0 else f"T{hours:+g}h", offset_hours=hours,
                                 timestamp=iso(row.time), latitude=float(row.lat), longitude=float(row.lon), wind_kmh=_kmh(row.wind_kt),
                                 pressure_hpa=_num(row.pressure_hpa), category=imd_category(_num(row.wind_kt))))
    chunk, page, page_size = _page(items, page, page_size)
    return HistoryPage(items=chunk, page=page, page_size=page_size, total=len(items))


def archive(region, subregion, year, page, page_size) -> ArchivePage:
    snap = _snapshot()
    storms = [s for s in snap.storms.values() if _in_selection(s, region, subregion) and (year is None or s.first_time.year == year)]
    storms.sort(key=lambda s: s.first_time, reverse=True)
    chunk, page, page_size = _page(storms, page, page_size)
    items = [HistoricalCycloneOut(id=s.storm_id, name=display_name(s.name), year=int(s.first_time.year), basin=s.basin,
                                  area=AREA_LABELS.get(s.area, s.basin), category=imd_category(s.peak_wind_kt), peak_wind_kmh=_kmh(s.peak_wind_kt),
                                  first_observed_at=iso(s.first_time), last_observed_at=iso(s.last_time), source=s.source) for s in chunk]
    return ArchivePage(items=items, page=page, page_size=page_size, total=len(storms))


def archive_summary() -> ArchiveSummaryOut:
    storms = list(_snapshot().storms.values())
    seasons = pd.Series([s.first_time.year for s in storms]).value_counts().sort_index()
    basins = sorted({s.basin for s in storms})
    return ArchiveSummaryOut(indexed_systems=len(storms), first_year=int(seasons.index.min()), last_year=int(seasons.index.max()),
                             coverage=f"MongoDB cyclone_database + held-out IBTrACS best track · basins {', '.join(basins)}",
                             seasons=[SeasonCount(season=str(y), storms=int(n)) for y, n in seasons.items()])


def regional_observation(region: str, subregion: str | None, at: str) -> RegionalObservationOut:
    when = _parse_time(at, "at")
    if when is None:
        raise MlServiceError("INVALID_TIME", "`at` is required (ISO 8601).", 400)
    snap = _snapshot()
    systems = []
    for storm in snap.storms.values():
        if not _in_selection(storm, region, subregion):
            continue
        gaps = (storm.fixes["time"] - when).abs()
        i = int(gaps.idxmin())
        if gaps.iloc[i] > OBSERVATION_WINDOW:
            continue
        fix = storm.fixes.iloc[i]
        systems.append(ObservedSystemOut(cyclone_id=storm.storm_id, code=storm.storm_id, name=display_name(storm.name),
                                         category=imd_category(_num(fix["wind_kt"])), status="historical", basin=storm.basin,
                                         region_id=storm.region_id, subregion_id=storm.subregion_id or None, latitude=float(fix["lat"]),
                                         longitude=float(fix["lon"]), wind_kmh=_kmh(fix["wind_kt"]), pressure_hpa=_num(fix["pressure_hpa"]),
                                         observed_at=iso(fix["time"])))
    systems.sort(key=lambda s: -(s.wind_kmh or -1))
    return RegionalObservationOut(region_id=region, subregion_id=subregion, timestamp=iso(when), active_systems=len(systems),
                                  systems=systems, strongest=systems[0] if systems else None)


def events(limit: int) -> list[EventOut]:
    storms = sorted(_snapshot().storms.values(), key=lambda s: s.last_time, reverse=True)[:max(1, min(limit, 100))]
    out = []
    for s in storms:
        last = s.fixes.iloc[-1]
        cat = imd_category(_num(last["wind_kt"]))
        out.append(EventOut(id=f"{s.storm_id}-{iso(s.last_time)}", title=f"{display_name(s.name)} ({s.basin}) last observed"
                            f"{f' as {cat}' if cat else ''} in the {AREA_LABELS.get(s.area, s.basin)}", source=s.source,
                            timestamp=iso(s.last_time), cyclone_id=s.storm_id))
    return out


# ---------------------------------------------------------------- regions (reference geography)

@lru_cache(maxsize=1)
def _reference(name: str) -> dict:
    return json.loads((REFERENCE / name).read_text(encoding="utf-8"))


def regions() -> list[dict]:
    return _reference("regions.json")["regions"]


def region(region_id: str) -> dict:
    found = next((r for r in regions() if r["id"] == region_id), None)
    if found is None:
        raise MlServiceError("REGION_NOT_FOUND", "Unknown region id.", 404)
    return found


def coastal_districts() -> list[dict]:
    return _reference("coastal_districts.json")["districts"]


# ---------------------------------------------------------------- satellite frame records

def _source_id(frame) -> str:
    return frame.source or UNRECORDED


def _channel(frame) -> str | None:
    if frame.channel:
        return frame.channel
    return "infrared" if frame.source == GRIDSAT else None  # GridSat-B1 as used here is its IR window (~11 µm) product


def frame_out(frame) -> dict:
    gridsat = frame.source == GRIDSAT
    return {
        "id": frame.frame_id, "regionId": frame.region_id, "subregionId": frame.subregion_id or None, "source": _source_id(frame),
        "channel": _channel(frame), "timestamp": iso(frame.time), "slotId": iso(frame.time), "imageUrl": frame.image_url,
        "bounds": None, "coverage": "Global 0.07° grid" if gridsat else None, "coverageTier": "primary" if gridsat else None,
        "resolution": "~8 km (0.07°)" if gridsat else None, "processingStatus": "processed" if frame.image_url else "missing",
        "processingLevel": None, "localSolarTime": None, "available": bool(frame.image_url),
        "unavailableReason": None if frame.image_url else "not_stored", "detections": [],
        "cycloneId": frame.storm_id or None, "datasetLabel": LABELS.get(frame.label),
        "latitude": _num(frame.latitude), "longitude": _num(frame.longitude),
    }


def _frames(region, subregion, source=None, channel=None) -> list:
    return [f for f in _snapshot().frames if _in_selection(f, region, subregion) and (not source or _source_id(f) == source)
            and (not channel or _channel(f) == channel)]


def satellite_sources(region: str, subregion: str | None) -> dict:
    frames = _frames(region, subregion)
    present = sorted({_source_id(f) for f in frames}, key=lambda s: s != GRIDSAT)
    if not present:
        return {"availability": None, "sources": []}
    coverage = [{"sourceId": s, "tier": "primary" if s == GRIDSAT else "secondary",
                 "note": f"{sum(1 for f in frames if _source_id(f) == s)} frame records in cyclone_database"} for s in present]
    return {"availability": {"regionId": region, "subregionId": subregion, "defaultSourceId": present[0], "sources": coverage},
            "sources": [SOURCES[s] for s in present]}


def satellite_frames(region, subregion, source, channel, start, end, page, page_size) -> dict:
    frames = _frames(region, subregion, source, channel)
    lo, hi = _parse_time(start, "start"), _parse_time(end, "end")
    if lo is not None or hi is not None:
        frames = [f for f in frames if (lo is None or f.time >= lo) and (hi is None or f.time <= hi)]
    else:
        frames = frames[-DEFAULT_FRAMES:]  # no range asked for: the latest frames only
    chunk, page, page_size = _page(frames, page, page_size)
    return {"items": [frame_out(f) for f in chunk], "page": page, "pageSize": page_size, "total": len(frames)}


def satellite_frame(frame_id: str) -> dict:
    found = next((f for f in _snapshot().frames if f.frame_id == frame_id), None)
    if found is None:
        raise MlServiceError("FRAME_NOT_FOUND", "No satellite frame record with this id.", 404)
    return frame_out(found)


def latest_frame(region: str | None) -> dict:
    frames = _frames(region, None)
    if not frames:
        raise MlServiceError("FRAME_NOT_FOUND", "No satellite frame records for this region.", 404)
    frame = frames[-1]
    source = SOURCES[_source_id(frame)]
    return {"id": frame.frame_id, "source": source["name"], "satellite": source["instrument"],
            "channel": "Infrared" if _channel(frame) == "infrared" else None, "capturedAt": iso(frame.time),
            "status": "processed" if frame.image_url else "unavailable", "region": AREA_LABELS.get(frame.area, frame.region_id),
            "resolutionKm": 8.0 if frame.source == GRIDSAT else None, "cloudTopTemperature": None, "enhancement": None,
            "datasetLabel": LABELS.get(frame.label)}
