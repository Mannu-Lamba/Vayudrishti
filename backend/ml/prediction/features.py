"""Observation validation, feature engineering and normalisation for the prediction model.

Canonical observation table (one row per storm fix, built by prediction_model/scripts/build_dataset.py
and served by backend/repositories/cyclone_repository.py):

    storm_id, time (UTC), lat, lon, wind_kt, pressure_hpa, nature, dist2land_km, area, …

Only fields that exist in the data are used. There is no SST, wind shear or humidity in the project,
so there are no environmental features beyond IBTrACS DIST2LAND; satellite features are not used
because no per-fix image embedding exists for every 6-hourly step (see prediction_model/README.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.prediction.config import SequenceConfig
from ml.prediction.geo import bearing_deg, haversine_km, wrap_lon

# UI areas (VayuDrishti hierarchy leaves). Arabian Sea / Bay of Bengal are views of the IBTrACS NI basin.
AREAS = ("arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific")
REQUIRED_COLUMNS = ("storm_id", "time", "lat", "lon", "wind_kt", "pressure_hpa", "nature", "dist2land_km", "area")

# Physically impossible values become missing (never clipped): no tropical cyclone on record exceeds
# ~185 kt or falls below 870 hPa.
WIND_VALID_KT = (0.0, 200.0)
PRESSURE_VALID_HPA = (850.0, 1050.0)

# (name, kind). "cont" = standardised with training statistics, missing → training mean (0 after
# standardisation) with a missing-indicator where missingness is common; "flag" = 0/1, passed through.
FEATURES: list[tuple[str, str]] = [
    ("lat", "cont"), ("rel_lat", "cont"), ("rel_lon", "cont"), ("sin_lon", "cont"), ("cos_lon", "cont"),
    ("dlat_prev", "cont"), ("dlon_prev", "cont"), ("speed_kmh", "cont"), ("dir_sin", "cont"), ("dir_cos", "cont"),
    ("motion_missing", "flag"),
    ("wind_kt", "cont"), ("wind_missing", "flag"), ("dwind_prev", "cont"),
    ("pressure_hpa", "cont"), ("pressure_missing", "flag"), ("dpres_prev", "cont"),
    ("dist2land_km", "cont"), ("age_h", "cont"), ("doy_sin", "cont"), ("doy_cos", "cont"),
    ("nature_tropical", "flag"), ("nature_extratropical", "flag"),
    *[(f"area_{area}", "flag") for area in AREAS],
]
FEATURE_NAMES = [name for name, _ in FEATURES]
FEATURE_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}
CONTINUOUS = np.array([kind == "cont" for _, kind in FEATURES])
# Per horizon: change of latitude (deg), longitude (deg, wrapped), wind (kt), pressure (hPa) from T0.
TARGETS = ("dlat", "dlon", "dwind", "dpres")


def validate_observations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Types, UTC timestamps, position/intensity sanity, duplicates, ordering. Returns (clean, report)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"observation table is missing columns: {missing}")
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True, errors="coerce")
    for col in ("lat", "lon", "wind_kt", "pressure_hpa", "dist2land_km"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    report: dict = {"rows_in": int(len(out))}

    bad_time = out["time"].isna()
    bad_pos = ~(np.isfinite(out["lat"]) & np.isfinite(out["lon"])) | (out["lat"].abs() > 90)
    report["dropped_invalid_time"] = int(bad_time.sum())
    report["dropped_invalid_position"] = int((bad_pos & ~bad_time).sum())
    out = out[~bad_time & ~bad_pos].copy()
    out["lon"] = wrap_lon(out["lon"].to_numpy())

    wind = out["wind_kt"]
    bad_wind = wind.notna() & ((wind < WIND_VALID_KT[0]) | (wind > WIND_VALID_KT[1]))
    out.loc[bad_wind, "wind_kt"] = np.nan
    report["wind_set_missing_out_of_range"] = int(bad_wind.sum())
    pres = out["pressure_hpa"]
    bad_pres = pres.notna() & ((pres < PRESSURE_VALID_HPA[0]) | (pres > PRESSURE_VALID_HPA[1]))
    out.loc[bad_pres, "pressure_hpa"] = np.nan
    report["pressure_set_missing_out_of_range"] = int(bad_pres.sum())

    dup = out.duplicated(["storm_id", "time"], keep="first")
    report["dropped_duplicate_times"] = int(dup.sum())
    out = out[~dup]
    out["nature"] = out["nature"].astype(str).str.strip().str.upper()
    out["area"] = out["area"].astype(str).where(out["area"].astype(str).isin(AREAS), "")
    out = out.sort_values(["storm_id", "time"]).reset_index(drop=True)
    report["rows_out"] = int(len(out))
    return out, report


def storm_hours(storm: pd.DataFrame) -> np.ndarray:
    """Hours since the storm's first fix (the storm is sorted by time)."""
    times = storm["time"]
    return ((times - times.iloc[0]).dt.total_seconds() / 3600.0).to_numpy(dtype=float)


def storm_fix_features(storm: pd.DataFrame, cfg: SequenceConfig) -> np.ndarray:
    """Per-fix features for one storm, [n, F]. Uses only the current and previous fix (causal).

    Motion/tendency features need the previous fix exactly one interval earlier; otherwise they are
    missing (NaN, flagged by motion_missing). rel_lat / rel_lon are window-relative and filled in by
    window_matrix.
    """
    n = len(storm)
    hours = storm_hours(storm)
    lat = storm["lat"].to_numpy(dtype=float)
    lon = storm["lon"].to_numpy(dtype=float)
    wind = storm["wind_kt"].to_numpy(dtype=float)
    pres = storm["pressure_hpa"].to_numpy(dtype=float)

    dt = np.full(n, np.nan)
    dt[1:] = np.diff(hours)
    with np.errstate(invalid="ignore"):
        regular = np.abs(dt - cfg.observation_interval_hours) * 60.0 <= cfg.time_tolerance_minutes
    prev_lat, prev_lon = np.roll(lat, 1), np.roll(lon, 1)
    prev_wind, prev_pres = np.roll(wind, 1), np.roll(pres, 1)
    dist = haversine_km(prev_lat, prev_lon, lat, lon)
    brg = np.radians(bearing_deg(prev_lat, prev_lon, lat, lon))
    moving = regular & (dist > 1e-6)

    feats = np.full((n, len(FEATURES)), np.nan)
    col = FEATURE_INDEX
    feats[:, col["lat"]] = lat
    feats[:, col["sin_lon"]] = np.sin(np.radians(lon))
    feats[:, col["cos_lon"]] = np.cos(np.radians(lon))
    feats[:, col["dlat_prev"]] = np.where(regular, lat - prev_lat, np.nan)
    feats[:, col["dlon_prev"]] = np.where(regular, wrap_lon(lon - prev_lon), np.nan)
    feats[:, col["speed_kmh"]] = np.where(regular, dist / np.where(regular, dt, 1.0), np.nan)
    feats[:, col["dir_sin"]] = np.where(regular, np.where(moving, np.sin(brg), 0.0), np.nan)
    feats[:, col["dir_cos"]] = np.where(regular, np.where(moving, np.cos(brg), 0.0), np.nan)
    feats[:, col["motion_missing"]] = (~regular).astype(float)
    feats[:, col["wind_kt"]] = wind
    feats[:, col["wind_missing"]] = np.isnan(wind).astype(float)
    feats[:, col["dwind_prev"]] = np.where(regular, wind - prev_wind, np.nan)
    feats[:, col["pressure_hpa"]] = pres
    feats[:, col["pressure_missing"]] = np.isnan(pres).astype(float)
    feats[:, col["dpres_prev"]] = np.where(regular, pres - prev_pres, np.nan)
    feats[:, col["dist2land_km"]] = storm["dist2land_km"].to_numpy(dtype=float)
    feats[:, col["age_h"]] = hours
    angle = 2.0 * np.pi * (storm["time"].dt.dayofyear.to_numpy(dtype=float) - 1.0) / 365.25
    feats[:, col["doy_sin"]] = np.sin(angle)
    feats[:, col["doy_cos"]] = np.cos(angle)
    nature = storm["nature"].astype(str).to_numpy()
    feats[:, col["nature_tropical"]] = (nature == "TS").astype(float)
    feats[:, col["nature_extratropical"]] = (nature == "ET").astype(float)
    area = storm["area"].astype(str).to_numpy()
    for name in AREAS:
        feats[:, col[f"area_{name}"]] = (area == name).astype(float)
    return feats


def window_matrix(fix: np.ndarray, lat: np.ndarray, lon: np.ndarray, end: int, steps: int) -> np.ndarray:
    """The input window ending at fix `end` (T0), [steps, F], with positions relative to T0."""
    start = end - steps + 1
    window = fix[start:end + 1].copy()
    window[:, FEATURE_INDEX["rel_lat"]] = lat[start:end + 1] - lat[end]
    window[:, FEATURE_INDEX["rel_lon"]] = wrap_lon(lon[start:end + 1] - lon[end])
    return window


@dataclass
class Normalizer:
    """Training-set statistics. Continuous features are standardised and missing values become 0 (the
    training mean); flags pass through. Targets are standardised per horizon and variable."""
    feature_mean: np.ndarray
    feature_std: np.ndarray
    target_mean: np.ndarray
    target_std: np.ndarray

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray) -> "Normalizer":
        flat = X.reshape(-1, X.shape[-1])
        mean = np.where(CONTINUOUS, np.nanmean(flat, axis=0), 0.0)
        std = np.where(CONTINUOUS, np.nanstd(flat, axis=0), 1.0)
        std[~np.isfinite(std) | (std < 1e-6)] = 1.0
        mean[~np.isfinite(mean)] = 0.0
        t_mean = np.nanmean(y, axis=0)
        t_std = np.nanstd(y, axis=0)
        t_std[~np.isfinite(t_std) | (t_std < 1e-6)] = 1.0
        t_mean[~np.isfinite(t_mean)] = 0.0
        return cls(mean, std, t_mean, t_std)

    def transform(self, X: np.ndarray) -> np.ndarray:
        return np.nan_to_num((X - self.feature_mean) / self.feature_std, nan=0.0).astype(np.float32)

    def normalize_targets(self, y: np.ndarray) -> np.ndarray:
        return ((y - self.target_mean) / self.target_std).astype(np.float32)

    def denormalize_targets(self, z: np.ndarray) -> np.ndarray:
        return z * self.target_std + self.target_mean

    def to_dict(self) -> dict:
        return {"feature_mean": self.feature_mean.tolist(), "feature_std": self.feature_std.tolist(),
                "target_mean": self.target_mean.tolist(), "target_std": self.target_std.tolist()}

    @classmethod
    def from_dict(cls, data: dict) -> "Normalizer":
        return cls(*(np.asarray(data[k], dtype=float) for k in ("feature_mean", "feature_std", "target_mean", "target_std")))
