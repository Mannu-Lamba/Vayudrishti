"""Forecast verification: per-horizon track error (great-circle km), lat/lon MAE, wind and pressure
errors, storm-level bootstrap confidence intervals and region-wise breakdowns."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.prediction.config import SequenceConfig
from ml.prediction.geo import haversine_km, wrap_lon

# (area id, meta column) in reporting order; region aggregates first, then their subregions.
EVALUATION_AREAS = [
    ("north_indian_ocean", "region", "North Indian Ocean"),
    ("arabian_sea", "subregion", "Arabian Sea"),
    ("bay_of_bengal", "subregion", "Bay of Bengal"),
    ("south_indian_ocean", "region", "South Indian Ocean"),
    ("pacific_ocean", "region", "Pacific Ocean"),
    ("western_pacific", "subregion", "Western Pacific"),
    ("eastern_pacific", "subregion", "Eastern Pacific"),
    ("southern_pacific", "subregion", "Southern Pacific"),
]


def forecast_errors(meta: pd.DataFrame, pred: np.ndarray, true: np.ndarray) -> dict[str, np.ndarray]:
    """pred/true: [N, H, 4] physical changes from T0. Returns [N, H] error arrays (NaN = no truth)."""
    lat0 = meta["lat0"].to_numpy(float)[:, None]
    lon0 = meta["lon0"].to_numpy(float)[:, None]
    track = haversine_km(lat0 + true[..., 0], lon0 + true[..., 1], lat0 + pred[..., 0], lon0 + pred[..., 1])
    return {
        "track_km": track,
        "lat_err_deg": pred[..., 0] - true[..., 0],
        "lon_err_deg": wrap_lon(pred[..., 1] - true[..., 1]),
        "wind_err_kt": np.where(np.isfinite(true[..., 2]), pred[..., 2] - true[..., 2], np.nan),
        "pres_err_hpa": np.where(np.isfinite(true[..., 3]), pred[..., 3] - true[..., 3], np.nan),
    }


def _stat(values: np.ndarray, fn) -> float | None:
    values = values[np.isfinite(values)]
    return round(float(fn(values)), 3) if len(values) else None


def summarize(errors: dict[str, np.ndarray], cfg: SequenceConfig, rows: np.ndarray | None = None) -> dict:
    """Per-horizon metrics (+ mean over horizons) for the selected rows."""
    sel = slice(None) if rows is None else rows
    out = {}
    for k, h in enumerate(cfg.horizons_hours):
        track = errors["track_km"][sel, k]
        wind = errors["wind_err_kt"][sel, k]
        pres = errors["pres_err_hpa"][sel, k]
        out[str(h)] = {
            "n": int(np.isfinite(track).sum()),
            "track_km_mean": _stat(track, np.mean),
            "track_km_median": _stat(track, np.median),
            "track_km_p90": _stat(track, lambda v: np.percentile(v, 90)),
            "mae_lat_deg": _stat(np.abs(errors["lat_err_deg"][sel, k]), np.mean),
            "mae_lon_deg": _stat(np.abs(errors["lon_err_deg"][sel, k]), np.mean),
            "n_wind": int(np.isfinite(wind).sum()),
            "wind_mae_kt": _stat(np.abs(wind), np.mean),
            "wind_rmse_kt": _stat(wind, lambda v: np.sqrt(np.mean(v ** 2))),
            "wind_bias_kt": _stat(wind, np.mean),
            "n_pressure": int(np.isfinite(pres).sum()),
            "pressure_mae_hpa": _stat(np.abs(pres), np.mean),
            "pressure_rmse_hpa": _stat(pres, lambda v: np.sqrt(np.mean(v ** 2))),
        }
    keys = ("track_km_mean", "wind_mae_kt", "pressure_mae_hpa")
    out["mean_over_horizons"] = {key: _mean([out[str(h)][key] for h in cfg.horizons_hours]) for key in keys}
    return out


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(float(np.mean(values)), 3) if values else None


def storm_bootstrap(values: np.ndarray, storms: np.ndarray, n_boot: int, seed: int) -> list[float] | None:
    """95 % CI of the mean, resampling whole storms (samples of one storm are correlated)."""
    ok = np.isfinite(values)
    values, storms = values[ok], storms[ok]
    if not len(values):
        return None
    ids, inverse = np.unique(storms, return_inverse=True)
    sums = np.bincount(inverse, weights=values)
    counts = np.bincount(inverse)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(ids), len(ids))
        means[b] = sums[pick].sum() / counts[pick].sum()
    return [round(float(np.percentile(means, 2.5)), 3), round(float(np.percentile(means, 97.5)), 3)]


def region_breakdown(errors: dict[str, np.ndarray], meta: pd.DataFrame, cfg: SequenceConfig, min_samples: int, min_storms: int) -> list[dict]:
    """Per-area metrics; areas with too few samples or storms report counts only."""
    rows = []
    for area, column, label in EVALUATION_AREAS:
        mask = (meta[column].astype(str) == area).to_numpy()
        n, storms = int(mask.sum()), int(meta.loc[mask, "storm_id"].nunique())
        entry = {"area": area, "label": label, "level": column, "samples": n, "storms": storms}
        if n < min_samples or storms < min_storms:
            entry["note"] = f"insufficient test data (needs ≥ {min_samples} samples and ≥ {min_storms} storms)"
            entry["metrics"] = None
        else:
            entry["metrics"] = summarize(errors, cfg, np.flatnonzero(mask))
        rows.append(entry)
    return rows
