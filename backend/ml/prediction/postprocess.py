"""Post-processing: model output (changes from T0) → validated, ordered, API-ready forecast steps.

Rules — every adjustment is recorded in the step's `flags`, nothing is changed silently:

1. Latitude must be finite and within [-90, 90]              → otherwise the forecast is rejected.
2. Longitude is wrapped into [-180, 180)                     → a representation change, not a clip.
3. Wind speed above 200 kt                                   → rejected (above any storm on record).
   Wind speed below 0 kt                                     → set to 0, flag `wind_floored_at_zero`.
4. Pressure outside [870, 1030] hPa                          → rejected (870 hPa = record low).
5. Timestamps are T0 + horizon, strictly increasing          → otherwise rejected.
6. Steps are ordered by horizon                              → by construction; checked.
7. Implied motion faster than 120 km/h between steps         → kept, flag `implausible_motion`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml.prediction.categories import imd_category
from ml.prediction.config import SequenceConfig
from ml.prediction.geo import haversine_km, wrap_lon

logger = logging.getLogger(__name__)
LAT_LIMIT = 90.0
WIND_MAX_KT = 200.0
PRESSURE_RANGE_HPA = (870.0, 1030.0)
MAX_PLAUSIBLE_SPEED_KMH = 120.0


class PostprocessingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ForecastStep:
    hours: int
    time: pd.Timestamp
    latitude: float
    longitude: float
    wind_kt: float
    pressure_hpa: float
    category: str | None
    uncertainty_radius_km: float | None = None
    wind_range_kt: tuple[float, float] | None = None
    flags: list[str] = field(default_factory=list)


def postprocess(anchor: dict, deltas: np.ndarray, cfg: SequenceConfig, uncertainty: dict | None = None) -> list[ForecastStep]:
    """anchor: T0 state (t0, lat0, lon0, wind0, pres0); deltas: [H, 4] physical changes from T0."""
    H = len(cfg.horizons_hours)
    if deltas.shape != (H, 4) or not np.all(np.isfinite(deltas)):
        raise PostprocessingError("INVALID_MODEL_OUTPUT", "The prediction model returned non-finite values.")
    radii = (uncertainty or {}).get("track_radius_km") or {}
    wind_err = (uncertainty or {}).get("wind_abs_error_kt") or {}
    t0: pd.Timestamp = anchor["t0"]
    steps: list[ForecastStep] = []
    prev_lat, prev_lon, prev_h = anchor["lat0"], anchor["lon0"], 0
    for k, hours in enumerate(cfg.horizons_hours):
        flags: list[str] = []
        lat = float(anchor["lat0"] + deltas[k, 0])
        lon = float(wrap_lon(anchor["lon0"] + deltas[k, 1]))
        if abs(lat) > LAT_LIMIT:
            raise PostprocessingError("PREDICTION_OUT_OF_RANGE", f"T+{hours}h latitude {lat:.2f} is outside [-90, 90].")
        wind = float(anchor["wind0"] + deltas[k, 2])
        if wind > WIND_MAX_KT:
            raise PostprocessingError("PREDICTION_OUT_OF_RANGE", f"T+{hours}h wind {wind:.0f} kt exceeds {WIND_MAX_KT:.0f} kt.")
        if wind < 0.0:
            wind = 0.0
            flags.append("wind_floored_at_zero")
        pres = float(anchor["pres0"] + deltas[k, 3])
        if not PRESSURE_RANGE_HPA[0] <= pres <= PRESSURE_RANGE_HPA[1]:
            raise PostprocessingError("PREDICTION_OUT_OF_RANGE", f"T+{hours}h pressure {pres:.0f} hPa is outside {PRESSURE_RANGE_HPA}.")
        speed = float(haversine_km(prev_lat, prev_lon, lat, lon)) / (hours - prev_h)
        if speed > MAX_PLAUSIBLE_SPEED_KMH:
            flags.append("implausible_motion")
        err = wind_err.get(str(hours))
        if flags:  # adjustments are returned in `flags` and logged, never applied silently
            logger.warning("Forecast %s from %s, T+%dh: %s", anchor.get("storm_id", "?"), t0, hours, ", ".join(flags))
        steps.append(ForecastStep(
            hours=hours, time=t0 + pd.Timedelta(hours=hours), latitude=lat, longitude=lon, wind_kt=wind, pressure_hpa=pres,
            category=imd_category(wind), uncertainty_radius_km=radii.get(str(hours)),
            wind_range_kt=None if err is None else (max(0.0, wind - err), wind + err), flags=flags,
        ))
        prev_lat, prev_lon, prev_h = lat, lon, hours
    times = [step.time for step in steps]
    if any(b <= a for a, b in zip(times, times[1:])) or times[0] <= t0:
        raise PostprocessingError("INVALID_FORECAST_SEQUENCE", "Forecast timestamps are not strictly increasing after the forecast time.")
    return steps
