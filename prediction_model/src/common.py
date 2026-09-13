"""Workspace helpers: config and paths, and access to the two pieces of shared code —

* backend/ml/prediction — the prediction core (features, sequences, baselines, model, post-processing)
  that the API serves with, so training and serving cannot drift apart;
* identification_model/src/utils.py — the existing IBTrACS basin → UI region mapping (ui_area).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
BACKEND = REPO / "backend"
IDENTIFICATION = REPO / "identification_model"
DEFAULT_CONFIG = ROOT / "configs" / "prediction.yaml"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
# The Windows console is cp1252: never let a non-ASCII character in a log line crash a finished run.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")

from ml.prediction.config import SequenceConfig  # noqa: E402


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def project_path(cfg: dict[str, Any], key: str, *parts: str) -> Path:
    base = Path(cfg["paths"][key])
    if not base.is_absolute():
        base = ROOT / base
    return base.joinpath(*parts)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value)}")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=_json_default)


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def set_seed(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def get_device():
    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'}")
    return device


def sequence_config(cfg: dict[str, Any]) -> SequenceConfig:
    return SequenceConfig.from_dict({**cfg["sequence"], **cfg.get("baseline", {})})


@lru_cache(maxsize=1)
def identification_utils():
    """identification_model/src/utils.py, loaded by path (its package name clashes with this `src`)."""
    spec = importlib.util.spec_from_file_location("vd_identification_utils", IDENTIFICATION / "src" / "utils.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
