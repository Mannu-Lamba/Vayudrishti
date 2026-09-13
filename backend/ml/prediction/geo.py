"""Great-circle geometry for track features and track-error evaluation (vectorised numpy)."""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_KM = 6371.0088  # IUGG mean Earth radius
KT_TO_KMH = 1.852
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def wrap_lon(lon):
    """Longitude (or longitude difference) into [-180, 180)."""
    return (np.asarray(lon, dtype=float) + 180.0) % 360.0 - 180.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km; correct across the antimeridian."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(wrap_lon(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float)))
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing from point 1 to point 2, degrees clockwise from north, [0, 360)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlmb = np.radians(wrap_lon(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float)))
    x = np.sin(dlmb) * np.cos(p2)
    y = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dlmb)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def compass_point(degrees: float | None) -> str | None:
    if degrees is None or not np.isfinite(degrees):
        return None
    return COMPASS[int((float(degrees) % 360.0) / 22.5 + 0.5) % 16]
