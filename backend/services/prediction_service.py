"""Prediction service: repository → sequence builder → inference → post-processing → response.

Routers call only this module. It never fabricates a forecast: missing model, unknown storm,
too little history or an implausible model output all surface as typed errors.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml.prediction.categories import imd_category
from ml.prediction.features import storm_hours
from ml.prediction.geo import KT_TO_KMH, compass_point, haversine_km
from ml.prediction.postprocess import PostprocessingError
from ml.prediction.sequences import SequenceInputError, is_regular, resolve_origin
from models.prediction import (
    CurrentStateOut, CycloneTrackOut, ForecastPointOut, PredictionCaseOut, PredictionCasesResponse, PredictionInputOut,
    PredictionModelOut, PredictionRequest, PredictionResponse, PredictionUncertaintyOut, TimingOut, TrackPointOut,
)
from repositories.cyclone_repository import RepositoryUnavailableError, mongo_repository, repository
from services.errors import MODEL_NOT_LOADED_MESSAGES, MlServiceError
from services.ml_registry import registry

logger = logging.getLogger(__name__)

SID_PATTERN = re.compile(r"^\d{7}[NS]\d{5}$")  # IBTrACS storm id, e.g. 2019300N12070
DATABASE_ID_PATTERN = re.compile(r"^SYS_[0-9a-f]{6,32}$")  # cyclone_database ids of samples without an IBTrACS SID
CACHE_SIZE = 256
POSITION_TOLERANCE_KM = 50.0  # IBTrACS positions are 0.1° (~11 km); a client echoing the observed fix is well inside
DISCLAIMER = ("AI-assisted decision support computed from the storm's best-track history. Not an official forecast: "
              "refer to IMD / the responsible RSMC for warnings.")
_cache: OrderedDict[tuple, PredictionResponse] = OrderedDict()
_cache_lock = threading.Lock()


def iso(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def engine():
    slot = registry.prediction
    if not slot.ready:
        raise MlServiceError("MODEL_NOT_LOADED", MODEL_NOT_LOADED_MESSAGES["prediction"], 503)
    return slot.instance


def _repo():
    if not repository.ready:
        raise MlServiceError("DATA_UNAVAILABLE", "Cyclone observation data is not available on the server.", 503)
    return repository


def _storm(cyclone_id: str) -> pd.DataFrame:
    """Validated observations of one storm: the held-out best-track table first (it carries every model input), then
    MongoDB cyclone_database (read-only) for any other storm. A database that cannot be checked is reported (503),
    never taken to mean "no such cyclone"."""
    if not (SID_PATTERN.fullmatch(cyclone_id or "") or DATABASE_ID_PATTERN.fullmatch(cyclone_id or "")):
        raise MlServiceError("INVALID_CYCLONE_ID", "Cyclone id must be an IBTrACS storm id such as 2019300N12070 "
                                                   "(or a cyclone_database id such as SYS_ae273011).", 400)
    storm = _repo().get_observations(cyclone_id)
    if storm is None:
        try:
            storm = mongo_repository.get_observations(cyclone_id)
        except RepositoryUnavailableError as exc:
            logger.warning("cyclone_database lookup for %s failed: %s", cyclone_id, exc)
            raise MlServiceError("DATABASE_UNAVAILABLE", "The cyclone database is not reachable, so this cyclone's observations "
                                                         "cannot be read.", 503) from None
    if storm is None:
        raise MlServiceError("CYCLONE_NOT_FOUND", "No observations are available for this cyclone.", 404)
    return storm


def _parse_time(value: str | None, field: str) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        raise MlServiceError("INVALID_TIME", f"`{field}` must be an ISO 8601 timestamp, e.g. 2019-10-25T00:00:00Z.", 400) from None
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def forecast_origins(storm: pd.DataFrame, cfg) -> list[pd.Timestamp]:
    """Fixes a forecast can start from: a complete, regular window and observed wind + pressure at T0."""
    hours = storm_hours(storm)
    wind, pres = storm["wind_kt"].to_numpy(float), storm["pressure_hpa"].to_numpy(float)
    return [storm["time"].iloc[i] for i in range(cfg.steps - 1, len(storm))
            if is_regular(hours[i - cfg.steps + 1:i + 1], cfg) and np.isfinite(wind[i]) and np.isfinite(pres[i])]


def list_cases(region: str | None, subregion: str | None, basin: str | None) -> PredictionCasesResponse:
    repo = _repo()
    slot = registry.prediction
    cfg = slot.instance.cfg if slot.ready else None
    cases = []
    for s in repo.list_storms(region, subregion, basin):
        origins = forecast_origins(repo.get_observations(s.storm_id), cfg) if cfg else []
        cases.append(PredictionCaseOut(
            cyclone_id=s.storm_id, name=s.name, season=s.season, basin=s.basin, region=s.region, subregion=s.subregion,
            area=s.area, first_observation=iso(s.first_time), last_observation=iso(s.last_time), observations=s.fixes,
            peak_wind_kt=s.peak_wind_kt, split=s.split, forecast_origins=[iso(t) for t in origins]))
    note = ("Held-out test storms from IBTrACS: the model never saw them, so each forecast can be compared with the real later track."
            if cfg else "The prediction model is not loaded, so no forecast origins are listed.")
    return PredictionCasesResponse(cases=cases, total=len(cases), note=note)


def track(cyclone_id: str, start: str | None, end: str | None) -> CycloneTrackOut:
    storm = _storm(cyclone_id)
    lo, hi = _parse_time(start, "start"), _parse_time(end, "end")
    if lo is not None:
        storm = storm[storm["time"] >= lo]
    if hi is not None:
        storm = storm[storm["time"] <= hi]
    points = [TrackPointOut(timestamp=iso(row.time), latitude=float(row.lat), longitude=float(row.lon),
                            wind_kmh=None if pd.isna(row.wind_kt) else round(float(row.wind_kt) * KT_TO_KMH, 1),
                            pressure_hpa=_num(row.pressure_hpa), category=imd_category(_num(row.wind_kt)))
              for row in storm.itertuples()]
    return CycloneTrackOut(cyclone_id=cyclone_id, observed_at=points[-1].timestamp if points else None, points=points)


def _current(anchor: dict, storm: pd.DataFrame, end_time: pd.Timestamp) -> CurrentStateOut:
    row = storm.loc[storm["time"] == end_time].iloc[0]
    speed_kt = _num(row.get("storm_speed_kt"))
    return CurrentStateOut(
        observed_at=iso(end_time), latitude=anchor["lat0"], longitude=anchor["lon0"],
        wind_kmh=round(anchor["wind0"] * KT_TO_KMH, 1), wind_kt=anchor["wind0"], pressure_hpa=anchor["pres0"],
        category=imd_category(anchor["wind0"]), nature=str(row["nature"]) or None,
        movement_direction=compass_point(_num(row.get("storm_dir_deg"))),
        movement_speed_kmh=None if speed_kt is None else round(speed_kt * KT_TO_KMH, 1),
    )


def predict(cyclone_id: str, at: str | None) -> PredictionResponse:
    started = time.perf_counter()
    eng = engine()
    storm = _storm(cyclone_id)
    at_ts = _parse_time(at, "at")
    try:
        origin = storm["time"].iloc[resolve_origin(storm, at_ts, eng.cfg)]
    except SequenceInputError as exc:
        raise MlServiceError(exc.code, exc.message, exc.status_code) from None
    key = (cyclone_id, origin.value, eng.info["version"], eng.info["trained_at"])
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit.model_copy(update={"cached": True})
    try:
        result = eng.predict(storm, at_ts)
    except SequenceInputError as exc:
        raise MlServiceError(exc.code, exc.message, exc.status_code) from None
    except PostprocessingError as exc:
        logger.warning("Prediction rejected by post-processing for %s at %s: %s", cyclone_id, origin, exc.message)
        raise MlServiceError(exc.code, "The model produced an implausible forecast for this time, so it is not shown.", 500) from None
    except Exception:
        logger.exception("Prediction inference failed for %s", cyclone_id)
        raise MlServiceError("INFERENCE_FAILED", "The prediction model could not process this cyclone.", 500) from None

    summary = _repo().get_summary(cyclone_id)
    unc = eng.uncertainty
    forecast = [ForecastPointOut(
        hours=s.hours, forecast_time=iso(s.time), latitude=round(s.latitude, 3), longitude=round(s.longitude, 3),
        wind_speed=round(s.wind_kt * KT_TO_KMH, 1), wind_speed_kt=round(s.wind_kt, 1), pressure=round(s.pressure_hpa, 1),
        category=s.category, confidence=None, uncertainty_radius_km=s.uncertainty_radius_km,
        wind_speed_range=None if s.wind_range_kt is None else [round(v * KT_TO_KMH, 1) for v in s.wind_range_kt],
        flags=s.flags) for s in result.steps]
    info = eng.info
    total_ms = (time.perf_counter() - started) * 1000
    response = PredictionResponse(
        cyclone_id=cyclone_id, name=summary.name if summary else "", basin=summary.basin if summary else "",
        region=summary.region if summary else "", subregion=summary.subregion if summary else "",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), issued_at=iso(result.origin),
        model_version=f"{info['display_name']} {info['version']} ({info['architecture']})",
        model=PredictionModelOut(name=info["name"], display_name=info["display_name"], version=info["version"],
                                 architecture=info["architecture"], trained_at=info["trained_at"], dataset_version=info["dataset_version"]),
        horizons_hours=info["horizons_hours"],
        input=PredictionInputOut(history_window_hours=eng.cfg.history_window_hours, observation_interval_hours=eng.cfg.observation_interval_hours,
                                 observations_used=result.observations_used, window_start=iso(result.window_start), window_end=iso(result.origin)),
        current=_current(result.anchor, storm, result.origin),
        forecast=forecast,
        uncertainty=None if not unc else PredictionUncertaintyOut(method="empirical", confidence_level=float(unc["quantile"]), note=unc["note"]),
        disclaimer=DISCLAIMER,
        inference=TimingOut(processing_time_ms=round(total_ms, 2), preprocessing_ms=round(result.preprocessing_ms, 2), model_ms=round(result.model_ms, 2)),
    )
    with _cache_lock:
        _cache[key] = response
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    logger.info("predict %s from %s -> %d steps in %.1f ms", cyclone_id, iso(result.origin), len(forecast), total_ms)
    return response


def predict_request(req: PredictionRequest) -> PredictionResponse:
    """POST /api/ml/predict: check the request against the loaded model and the observed track, then run the
    same predict() path as GET /api/cyclones/{id}/prediction (same cache, same response contract)."""
    eng = engine()
    model_horizons = list(eng.info["horizons_hours"])
    if req.horizons_hours is not None:
        unsupported = sorted(set(req.horizons_hours) - set(model_horizons))
        if unsupported:
            raise MlServiceError("UNSUPPORTED_HORIZON", f"The model forecasts {', '.join(map(str, model_horizons))} h ahead; "
                                                        f"{', '.join(map(str, unsupported))} h is not available.", 400)
    at = None if req.timestamp is None else req.timestamp.isoformat()
    if req.latitude is not None and req.longitude is not None:
        storm = _storm(req.cyclone_id)
        try:
            fix = storm.iloc[resolve_origin(storm, _parse_time(at, "timestamp"), eng.cfg)]
        except SequenceInputError as exc:
            raise MlServiceError(exc.code, exc.message, exc.status_code) from None
        distance = float(haversine_km(req.latitude, req.longitude, fix["lat"], fix["lon"]))
        if distance > POSITION_TOLERANCE_KM:
            raise MlServiceError(
                "POSITION_MISMATCH", f"The given position is {distance:.0f} km from this cyclone's observed position at {iso(fix['time'])} "
                                     f"({fix['lat']:.1f}, {fix['lon']:.1f}). Forecasts start from the observed fix.", 400)
    response = predict(req.cyclone_id, at)
    if req.horizons_hours is None:
        return response
    keep = set(req.horizons_hours)
    return response.model_copy(update={"forecast": [step for step in response.forecast if step.hours in keep],
                                       "horizons_hours": [hours for hours in model_horizons if hours in keep]})
