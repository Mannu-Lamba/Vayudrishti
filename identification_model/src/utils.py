"""Shared helpers: configuration, paths, seeding, device, hashing and region mapping."""

from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "config.yaml"

# Label index = position. 0 = NO_CYCLONE, 1 = CYCLONE.
CLASS_NAMES = ["no_cyclone", "cyclone"]
DISPLAY_NAMES = ["NO_CYCLONE", "CYCLONE"]


# --------------------------------------------------------------------------- config / paths

def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def project_path(cfg: dict[str, Any], key: str, *parts: str) -> Path:
    """Resolve a `paths:` entry (relative to identification_model/) and optional sub-parts."""
    base = Path(cfg["paths"][key])
    if not base.is_absolute():
        base = ROOT / base
    return base.joinpath(*parts)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def cfg_file(cfg: dict[str, Any], key: str, default: str) -> str:
    """Task-specific file name from the config's `files:` section, else the identification default."""
    return cfg.get("files", {}).get(key, default)


def split_path(cfg: dict[str, Any], split: str) -> Path:
    pattern = cfg.get("splits", {}).get("file_pattern", "{split}.csv")
    return project_path(cfg, "splits", pattern.format(split=split))


def is_multiclass(cfg: dict[str, Any]) -> bool:
    return cfg.get("task") == "multiclass"


def task_classes(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """[{id, code, name, ...}] for the task; the binary identification task has no `classes:` section."""
    if cfg.get("classes"):
        return sorted(cfg["classes"], key=lambda c: c["id"])
    return [{"id": i, "code": DISPLAY_NAMES[i], "name": CLASS_NAMES[i]} for i in range(len(CLASS_NAMES))]


WIND_SOURCE = "IBTrACS USA_WIND (JTWC/NHC 1-min sustained)"


def class_mapping_json(classes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{id: {code, name[, imd_categories, wind_kt, wind_source]}} — the single class_mapping.json schema,
    written by prepare_candidates and train, read by the backend (backend/ml/classification/model.py)."""
    out = {}
    for c in classes:
        entry = {"code": c["code"], "name": c["name"]}
        if "imd" in c:
            entry.update(imd_categories=list(c["imd"]), wind_kt=[c.get("min_kt"), c.get("max_kt")], wind_source=WIND_SOURCE)
        out[str(c["id"])] = entry
    return out


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=_json_default)


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


# --------------------------------------------------------------------------- reproducibility

def set_seed(seed: int, deterministic: bool = True) -> None:
    """Seed Python, NumPy and PyTorch (CPU + CUDA)."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)


def get_device(verbose: bool = True):
    """CUDA → MPS → CPU. Never fails when a GPU is absent."""
    import torch

    if torch.cuda.is_available():
        device, name = torch.device("cuda"), torch.cuda.get_device_name(0)
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device, name = torch.device("mps"), "Apple MPS"
    else:
        device, name = torch.device("cpu"), "CPU"
    if verbose:
        print(f"Device:\n{name}")
    return device


# --------------------------------------------------------------------------- hashing

def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def pixel_sha256(arr: np.ndarray) -> str:
    """Hash of decoded pixels, so re-encoded copies of the same image still match."""
    arr = np.ascontiguousarray(arr)
    return hashlib.sha256(str(arr.shape).encode() + arr.tobytes()).hexdigest()


def dhash(arr: np.ndarray, size: int = 8) -> int:
    """64-bit difference hash of a grayscale uint8 image."""
    from PIL import Image

    small = np.asarray(Image.fromarray(arr).resize((size + 1, size), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def thumbnail(arr: np.ndarray, size: int = 32) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.fromarray(arr).resize((size, size), Image.Resampling.BILINEAR), dtype=np.float32)


def near_duplicate_pairs(hashes: list[int], thumbs: np.ndarray, max_hamming: int, min_corr: float,
                         chunk: int = 1024) -> list[tuple[int, int, int, float]]:
    """Pairs (i, j, hamming, corr) whose dHash distance <= max_hamming AND whose thumbnails
    correlate >= min_corr. The second test removes hash collisions between smooth, unrelated scenes."""
    n = len(hashes)
    if n < 2:
        return []
    bits = np.array([[(h >> (63 - k)) & 1 for k in range(64)] for h in hashes], dtype=np.float32)
    flat = thumbs.reshape(n, -1).astype(np.float32)
    flat = flat - flat.mean(axis=1, keepdims=True)
    flat /= np.linalg.norm(flat, axis=1, keepdims=True) + 1e-6
    pairs: list[tuple[int, int, int, float]] = []
    for start in range(0, n, chunk):
        block = bits[start:start + chunk]
        ham = 64 - (block @ bits.T + (1 - block) @ (1 - bits).T)
        for bi, j in np.argwhere(ham <= max_hamming):
            i = start + int(bi)
            if j <= i:
                continue
            corr = float(flat[i] @ flat[j])
            if corr >= min_corr:
                pairs.append((i, int(j), int(round(ham[bi, j])), corr))
    return pairs


# --------------------------------------------------------------------------- intensity

def intensity_from_max_wind(max_wind_kt: float) -> str:
    """Storm-level intensity class used by the PS-70 positive candidate workbook.

    Reproduces its `intensity_category` from the storm's lifetime maximum wind (knots; WMO first,
    USA when WMO is missing): < 34 kt weak, 34–63 kt medium, >= 64 kt strong. These are the WMO
    gale / hurricane-force boundaries; audit_datasets.py verifies the rule against the workbook.
    """
    if max_wind_kt is None or not np.isfinite(max_wind_kt):
        return ""
    if max_wind_kt < 34:
        return "weak"
    if max_wind_kt < 64:
        return "medium"
    return "strong"


# --------------------------------------------------------------------------- regions

# IBTrACS basin → VayuDrishti UI hierarchy (same ids as the frontend). Region ids are never basin
# codes; the Arabian Sea is a subregion of the North Indian Ocean, never an IBTrACS basin.
REGION_OF_BASIN = {
    "NI": "north_indian_ocean",
    "SI": "south_indian_ocean",
    "WP": "pacific_ocean",
    "EP": "pacific_ocean",
    "SP": "pacific_ocean",
}
SUBREGION_OF_BASIN = {"WP": "western_pacific", "EP": "eastern_pacific", "SP": "southern_pacific"}
NI_SUBBASIN = {"AS": "arabian_sea", "BB": "bay_of_bengal"}
# In dataset A (IBTrACS) NI subbasin AS spans 41.8–78.0°E and BB 78.0–100.0°E; the frontend's
# subregion bounds split at the same meridian. Used only when a record has no subbasin (negatives).
AS_BB_BOUNDARY_LON = 78.0

AREA_LABELS = {
    "north_indian_ocean": "North Indian Ocean",
    "arabian_sea": "Arabian Sea",
    "bay_of_bengal": "Bay of Bengal",
    "south_indian_ocean": "South Indian Ocean",
    "pacific_ocean": "Pacific Ocean",
    "western_pacific": "Western Pacific",
    "eastern_pacific": "Eastern Pacific",
    "southern_pacific": "Southern Pacific",
}
# (area id, column it is matched on) in reporting order.
EVALUATION_AREAS = [
    ("north_indian_ocean", "region"),
    ("arabian_sea", "subregion"),
    ("bay_of_bengal", "subregion"),
    ("south_indian_ocean", "region"),
    ("pacific_ocean", "region"),
    ("western_pacific", "subregion"),
    ("eastern_pacific", "subregion"),
    ("southern_pacific", "subregion"),
]


def ui_area(basin: str, subbasin: str | None = None, lon: float | None = None) -> tuple[str, str]:
    """Return (region, subregion) UI ids for an IBTrACS basin (+ subbasin or longitude for NI)."""
    basin = str(basin).strip().upper()
    region = REGION_OF_BASIN.get(basin, "unknown")
    if basin == "NI":
        sub = NI_SUBBASIN.get(str(subbasin).strip().upper()) if isinstance(subbasin, str) else None
        if sub is None and lon is not None and np.isfinite(lon):
            sub = "arabian_sea" if float(lon) < AS_BB_BOUNDARY_LON else "bay_of_bengal"
        return region, sub or ""
    return region, SUBREGION_OF_BASIN.get(basin, "")


# --------------------------------------------------------------------------- geometry / time

def angular_distance_deg(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in degrees (vectorised)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(np.asarray(lon2) - np.asarray(lon1))
    cos = np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dlon)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def wrap_dlon(dlon) -> np.ndarray:
    return (np.asarray(dlon, dtype=float) + 180.0) % 360.0 - 180.0


def iso_utc(ts) -> str:
    import pandas as pd

    if ts is None or (isinstance(ts, float) and np.isnan(ts)) or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
