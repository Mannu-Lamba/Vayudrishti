"""Load and validate the classification model artifacts (backend/models/classification/)."""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn

from ml.architecture import load_network, self_check
from ml.imaging import input_size

REQUIRED_FILES = ("best_model.pth", "model_config.json", "class_mapping.json")


class ModelArtifactsError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def load_classification_model(model_dir: Path, device: torch.device) -> tuple[nn.Module, dict, list[dict]]:
    """→ (network in eval mode, model_config, classes ordered by id). Raises ModelArtifactsError."""
    missing = [name for name in REQUIRED_FILES if not (model_dir / name).exists()]
    if missing:
        raise ModelArtifactsError("MODEL_FILE_MISSING", f"Classification model files missing in {model_dir}: {', '.join(missing)}")
    config = json.loads((model_dir / "model_config.json").read_text(encoding="utf-8"))
    mapping = json.loads((model_dir / "class_mapping.json").read_text(encoding="utf-8"))
    classes = [{"id": int(k), **v} for k, v in sorted(mapping.items(), key=lambda kv: int(kv[0]))]
    if [c["id"] for c in classes] != list(range(len(classes))):
        raise ModelArtifactsError("INVALID_CLASS_MAPPING", "class_mapping.json ids must be 0..N-1")
    try:
        model, ckpt = load_network(model_dir / "best_model.pth", device)
    except Exception as exc:
        raise ModelArtifactsError("MODEL_LOAD_FAILED", f"Could not load the classification checkpoint: {exc}") from exc
    if int(ckpt["num_classes"]) != len(classes) or int(config.get("number_of_classes", len(classes))) != len(classes):
        raise ModelArtifactsError("INVALID_CLASS_MAPPING", "Checkpoint, model_config.json and class_mapping.json disagree on the number of classes")
    height, width = input_size(config)
    try:
        self_check(model, (1, 3, height, width), (1, len(classes)), device)
    except Exception as exc:
        raise ModelArtifactsError("MODEL_SELF_CHECK_FAILED", f"The classification model failed its load-time check: {exc}") from exc
    return model, config, classes
