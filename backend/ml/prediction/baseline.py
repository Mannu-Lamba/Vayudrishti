"""Reference forecasts the learned model must beat.

Both return changes from T0 in the model's target layout [N, H, 4] (dlat, dlon, dwind, dpres):

* persistence   — the storm stays where and as it is (all changes 0);
* extrapolation — the mean motion of the last `motion_window_hours` continues unchanged; intensity
                  and pressure persist.
"""

from __future__ import annotations

import numpy as np

from ml.prediction.config import SequenceConfig
from ml.prediction.features import FEATURE_INDEX


def persistence(n: int, cfg: SequenceConfig) -> np.ndarray:
    return np.zeros((n, len(cfg.horizons_hours), 4), dtype=np.float32)


def extrapolation(X_raw: np.ndarray, cfg: SequenceConfig) -> np.ndarray:
    """X_raw: [N, steps, F] un-normalised windows (positions relative to T0 are always present)."""
    k = cfg.motion_window_hours // cfg.observation_interval_hours
    past = cfg.steps - 1 - k
    per_step_lat = -X_raw[:, past, FEATURE_INDEX["rel_lat"]] / k   # lat(T0) - lat(T0 - k·interval), per interval
    per_step_lon = -X_raw[:, past, FEATURE_INDEX["rel_lon"]] / k
    out = persistence(len(X_raw), cfg)
    for h_idx, steps_ahead in enumerate(cfg.horizon_steps):
        out[:, h_idx, 0] = per_step_lat * steps_ahead
        out[:, h_idx, 1] = per_step_lon * steps_ahead
    return out


BASELINES = {"persistence": lambda X, cfg: persistence(len(X), cfg), "extrapolation": extrapolation}
