"""IdentificationInference — the stage-1 model trained in identification_model/ (binary)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image

from ml.architecture import check_probabilities, load_network, self_check
from ml.classification.model import ModelArtifactsError
from ml.classification.preprocessing import PreprocessingError
from ml.imaging import input_size, to_model_tensor

logger = logging.getLogger(__name__)
REQUIRED_FILES = ("best_model.pth", "model_config.json")


@dataclass
class IdentificationResult:
    detected: bool
    class_name: str                 # "CYCLONE" | "NO_CYCLONE"
    confidence: float               # probability of the predicted class
    cyclone_probability: float
    probabilities: dict[str, float]
    threshold: float
    preprocessing_ms: float
    model_ms: float


class IdentificationInference:
    NAME = "cyclone-identification"

    def __init__(self, model_dir: Path, device: str | None = None):
        started = time.perf_counter()
        model_dir = Path(model_dir)
        missing = [name for name in REQUIRED_FILES if not (model_dir / name).exists()]
        if missing:
            raise ModelArtifactsError("MODEL_FILE_MISSING", f"Identification model files missing in {model_dir}: {', '.join(missing)}")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.config = json.loads((model_dir / "model_config.json").read_text(encoding="utf-8"))
        try:
            self.model, ckpt = load_network(model_dir / "best_model.pth", self.device)
        except Exception as exc:
            raise ModelArtifactsError("MODEL_LOAD_FAILED", f"Could not load the identification checkpoint: {exc}") from exc
        if int(ckpt["num_classes"]) != 2:
            raise ModelArtifactsError("INVALID_CLASS_MAPPING", "The identification model must have 2 classes")
        height, width = input_size(self.config)
        try:
            self_check(self.model, (1, 3, height, width), (1, 2), self.device)
        except Exception as exc:
            raise ModelArtifactsError("MODEL_SELF_CHECK_FAILED", f"The identification model failed its load-time check: {exc}") from exc
        self.threshold = float(self.config.get("decision_threshold") or 0.5)
        self.load_time_ms = (time.perf_counter() - started) * 1000
        self.info = {
            "name": self.NAME,
            "version": str(self.config.get("model_version", "v1")),
            "architecture": str(self.config.get("architecture")),
            "dataset_version": self.config.get("dataset_version"),
            "trained_at": self.config.get("created_at"),
        }
        logger.info("Identification model loaded on %s in %.0f ms", self.device, self.load_time_ms)

    @torch.inference_mode()
    def predict(self, image: Image.Image) -> IdentificationResult:
        t0 = time.perf_counter()
        try:
            x = to_model_tensor(image, self.config).to(self.device)
        except Exception as exc:
            raise PreprocessingError(str(exc)) from exc
        t1 = time.perf_counter()
        probs = torch.softmax(self.model(x).float(), dim=1)[0].cpu()
        t2 = time.perf_counter()
        check_probabilities(probs, 2)
        p_cyclone = float(probs[1])
        detected = p_cyclone >= self.threshold
        return IdentificationResult(
            detected=detected, class_name="CYCLONE" if detected else "NO_CYCLONE",
            confidence=p_cyclone if detected else float(probs[0]), cyclone_probability=p_cyclone,
            probabilities={"NO_CYCLONE": float(probs[0]), "CYCLONE": p_cyclone}, threshold=self.threshold,
            preprocessing_ms=(t1 - t0) * 1000, model_ms=(t2 - t1) * 1000,
        )
