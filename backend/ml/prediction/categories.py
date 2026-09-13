"""IMD intensity category of a wind speed — the scale the project uses in every basin.

Applied to the 1-minute IBTrACS USA_WIND (the wind the model is trained on), exactly as the
classification labels are. IMD itself uses a 3-minute wind, so near a threshold the category can
differ from an official IMD bulletin.
"""

from __future__ import annotations

import math

# (lower bound in knots, IMD category), strongest first. D 17–27, DD 28–33, CS 34–47, SCS 48–63,
# VSCS 64–89, ESCS 90–119, SuCS ≥ 120.
IMD_THRESHOLDS_KT = (
    (120, "Super Cyclonic Storm"),
    (90, "Extremely Severe Cyclonic Storm"),
    (64, "Very Severe Cyclonic Storm"),
    (48, "Severe Cyclonic Storm"),
    (34, "Cyclonic Storm"),
    (28, "Deep Depression"),
    (17, "Depression"),
)
BELOW_DEPRESSION = "Low Pressure Area"


def imd_category(wind_kt: float | None) -> str | None:
    if wind_kt is None or not math.isfinite(wind_kt):
        return None
    for threshold, name in IMD_THRESHOLDS_KT:
        if wind_kt >= threshold:
            return name
    return BELOW_DEPRESSION
