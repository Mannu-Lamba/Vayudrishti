"""Temporal sequence construction.

Training: every fix T0 of a storm whose preceding window (T-24 … T0) is complete and regular, and
whose future positions at every horizon exist, becomes one sample. Serving: the window ending at the
requested forecast time. Both go through window_matrix, so inputs are identical.

Matching rule (documented, never silent): fixes must lie on the regular 6-hourly grid within
`time_tolerance_minutes` (0 for IBTrACS synoptic fixes); a gap anywhere in the window makes it
unusable. Targets are matched by timestamp, not by row position.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ml.prediction.config import SequenceConfig
from ml.prediction.features import FEATURES, storm_fix_features, storm_hours, window_matrix
from ml.prediction.geo import wrap_lon


class SequenceInputError(ValueError):
    """The observations cannot form a valid input window (maps to a 4xx response)."""

    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


INSUFFICIENT_HISTORY_MESSAGE = "Insufficient historical observations for the selected cyclone."


@dataclass
class SequenceSet:
    X: np.ndarray                 # [N, steps, F] raw features (NaN = missing)
    y: np.ndarray                 # [N, H, 4] dlat, dlon, dwind, dpres (NaN = missing target)
    meta: pd.DataFrame            # one row per sample: storm_id, t0, area, region, subregion, basin, lat0, …
    skipped: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.meta)


def is_regular(hours: np.ndarray, cfg: SequenceConfig) -> bool:
    gaps = np.diff(hours)
    return bool(np.all(np.abs(gaps - cfg.observation_interval_hours) * 60.0 <= cfg.time_tolerance_minutes))


def _find_time(hours: np.ndarray, target: float, tolerance_h: float) -> int | None:
    pos = int(np.searchsorted(hours, target - tolerance_h - 1e-9))
    if pos < len(hours) and abs(hours[pos] - target) <= tolerance_h + 1e-9:
        return pos
    return None


def _anchor(storm: pd.DataFrame, i: int, fix: np.ndarray) -> dict:
    row = storm.iloc[i]
    return {
        "storm_id": row["storm_id"], "t0": row["time"], "lat0": float(row["lat"]), "lon0": float(row["lon"]),
        "wind0": float(row["wind_kt"]), "pres0": float(row["pressure_hpa"]), "nature0": row["nature"],
        "area": row["area"], "region": row.get("region", ""), "subregion": row.get("subregion", ""), "basin": row.get("basin", ""),
    }


def build_samples(obs: pd.DataFrame, cfg: SequenceConfig) -> SequenceSet:
    """All training/evaluation samples of a validated observation table."""
    steps, H = cfg.steps, len(cfg.horizons_hours)
    tol_h = cfg.time_tolerance_minutes / 60.0
    X, Y, meta = [], [], []
    skipped: Counter = Counter()
    for _, storm in obs.groupby("storm_id", sort=False):
        storm = storm.sort_values("time").reset_index(drop=True)
        n = len(storm)
        if n < steps + 1:
            skipped["storm_too_short"] += max(n, 0)
            continue
        hours = storm_hours(storm)
        fix = storm_fix_features(storm, cfg)
        lat, lon = storm["lat"].to_numpy(float), storm["lon"].to_numpy(float)
        wind, pres = storm["wind_kt"].to_numpy(float), storm["pressure_hpa"].to_numpy(float)
        for i in range(steps - 1, n):
            if not is_regular(hours[i - steps + 1:i + 1], cfg):
                skipped["irregular_window"] += 1
                continue
            y = np.full((H, 4), np.nan)
            complete = True
            for k, h in enumerate(cfg.horizons_hours):
                j = _find_time(hours, hours[i] + h, tol_h)
                if j is None:
                    complete = False
                    break
                y[k] = (lat[j] - lat[i], wrap_lon(lon[j] - lon[i]), wind[j] - wind[i], pres[j] - pres[i])
            if not complete:
                skipped["future_position_missing"] += 1
                continue
            X.append(window_matrix(fix, lat, lon, i, steps))
            Y.append(y)
            meta.append(_anchor(storm, i, fix))
    F = len(FEATURES)
    return SequenceSet(
        X=np.asarray(X, dtype=np.float32).reshape(-1, steps, F),
        y=np.asarray(Y, dtype=np.float32).reshape(-1, H, 4),
        meta=pd.DataFrame(meta),
        skipped=dict(skipped),
    )


def resolve_origin(storm: pd.DataFrame, at: pd.Timestamp | None, cfg: SequenceConfig) -> int:
    """Index of the forecast origin T0: the latest fix at or before `at` (default: the newest fix),
    at most `origin_tolerance_hours` older than `at`."""
    if storm.empty:
        raise SequenceInputError("OBSERVATION_NOT_FOUND", "The cyclone has no observations.", 404)
    times = storm["time"]
    if at is None:
        return len(storm) - 1
    candidates = np.flatnonzero((times <= at).to_numpy())
    if not len(candidates):
        raise SequenceInputError("OBSERVATION_NOT_FOUND", "There is no observation of this cyclone at or before the requested time.", 404)
    idx = int(candidates[-1])
    if (at - times.iloc[idx]).total_seconds() / 3600.0 > cfg.origin_tolerance_hours:
        raise SequenceInputError(
            "OBSERVATION_NOT_FOUND",
            f"No observation within {cfg.origin_tolerance_hours:g} h of the requested time; the storm's record may have ended.", 404)
    return idx


def build_inference_window(storm: pd.DataFrame, end: int, cfg: SequenceConfig) -> tuple[np.ndarray, dict]:
    """Input window ending at fix `end` of one validated, time-sorted storm → ([steps, F], anchor).

    Only fixes up to T0 are used (causal). Raises SequenceInputError INSUFFICIENT_HISTORY when the
    window is incomplete or irregular.
    """
    steps = cfg.steps
    storm = storm.iloc[:end + 1].reset_index(drop=True)
    if len(storm) < steps:
        raise SequenceInputError(
            "INSUFFICIENT_HISTORY",
            f"{INSUFFICIENT_HISTORY_MESSAGE} The model needs {steps} observations covering the previous "
            f"{cfg.history_window_hours} h; only {len(storm)} exist before this time.")
    hours = storm_hours(storm)
    if not is_regular(hours[-steps:], cfg):
        raise SequenceInputError(
            "INSUFFICIENT_HISTORY",
            f"{INSUFFICIENT_HISTORY_MESSAGE} The previous {cfg.history_window_hours} h are not continuously "
            f"observed every {cfg.observation_interval_hours} h.")
    fix = storm_fix_features(storm, cfg)
    lat, lon = storm["lat"].to_numpy(float), storm["lon"].to_numpy(float)
    i = len(storm) - 1
    return window_matrix(fix, lat, lon, i, steps), _anchor(storm, i, fix)


# Inputs the model never saw missing in training (IBTrACS DIST2LAND is 0 % missing, NATURE is always reported), so
# they are required and never imputed. Wind/pressure gaps inside the window are handled exactly as in training (a
# missing-flag feature); at T0 both must be observed (MISSING_CURRENT_INTENSITY, checked by the inference class).
REQUIRED_WINDOW_FIELDS = (("dist2land_km", "distance to land"), ("nature", "storm nature (NATURE)"))
_UNSET_TEXT = {"", "NAN", "NONE"}


def missing_required_features(storm: pd.DataFrame, end: int, cfg: SequenceConfig) -> list[str]:
    """Labels of required inputs absent anywhere in the window ending at fix `end` (empty list = complete)."""
    window = storm.iloc[max(0, end - cfg.steps + 1):end + 1]
    missing = []
    for column, label in REQUIRED_WINDOW_FIELDS:
        if column not in window.columns:
            missing.append(label)
            continue
        values = window[column]
        absent = values.astype(str).str.strip().str.upper().isin(_UNSET_TEXT) if column == "nature" else values.isna()
        if bool(absent.any()):
            missing.append(label)
    return missing
