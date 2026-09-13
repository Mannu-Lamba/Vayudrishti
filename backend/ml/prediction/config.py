"""Temporal window and forecast horizons — the only place these numbers are defined.

Training reads them from prediction_model/configs/prediction.yaml; serving reads the copy frozen into
backend/models/prediction/model_config.json, so a model is always served with the window it was
trained on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class SequenceConfig:
    history_window_hours: int = 24          # T-24h … T0
    observation_interval_hours: int = 6     # IBTrACS synoptic fixes
    horizons_hours: tuple[int, ...] = (6, 12, 18, 24)
    time_tolerance_minutes: int = 0         # allowed deviation of a fix from the regular 6-hourly grid
    origin_tolerance_hours: float = 3.0     # a requested forecast time snaps to the latest fix at most this old
    motion_window_hours: int = 12           # extrapolation baseline: mean motion over the last 12 h

    def __post_init__(self) -> None:
        interval = int(self.observation_interval_hours)
        if interval <= 0 or self.history_window_hours < interval or self.history_window_hours % interval:
            raise ValueError("history_window_hours must be a positive multiple of observation_interval_hours")
        horizons = tuple(int(h) for h in self.horizons_hours)
        if not horizons or list(horizons) != sorted(set(horizons)) or any(h <= 0 or h % interval for h in horizons):
            raise ValueError("horizons_hours must be sorted, unique, positive multiples of observation_interval_hours")
        if self.motion_window_hours % interval or not interval <= self.motion_window_hours <= self.history_window_hours:
            raise ValueError("motion_window_hours must be a multiple of the interval inside the history window")
        object.__setattr__(self, "horizons_hours", horizons)

    @property
    def steps(self) -> int:
        """Observations in one input window (T-24 … T0 at 6 h → 5)."""
        return self.history_window_hours // self.observation_interval_hours + 1

    @property
    def horizon_steps(self) -> tuple[int, ...]:
        return tuple(h // self.observation_interval_hours for h in self.horizons_hours)

    @classmethod
    def from_dict(cls, data: dict) -> "SequenceConfig":
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if "horizons_hours" in values:
            values["horizons_hours"] = tuple(values["horizons_hours"])
        return cls(**values)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["horizons_hours"] = list(self.horizons_hours)
        return data
