"""ClassificationInference — load once, classify many.

Returns the IMD intensity class, its confidence (max softmax) and the full probability
distribution. All values come from the trained network; nothing is hardcoded.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch
from PIL import Image

from ml.architecture import check_probabilities
from ml.classification.model import load_classification_model
from ml.classification.preprocessing import preprocess_image

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    class_id: int
    class_code: str
    class_name: str
    confidence: float
    probabilities: dict[str, float]          # class name → probability (sums to 1)
    preprocessing_ms: float
    model_ms: float
    imd_categories: list[str] = field(default_factory=list)
    wind_kt_range: list | None = None        # [low, high] kt of the predicted class (class_mapping.json); high None = open


class ClassificationInference:
    NAME = "cyclone-classification"

    def __init__(self, model_dir: Path, device: str | None = None):
        started = time.perf_counter()
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model, self.config, self.classes = load_classification_model(Path(model_dir), self.device)
        self.load_time_ms = (time.perf_counter() - started) * 1000
        self.info = {
            "name": self.NAME,
            "version": str(self.config.get("model_version", "v1")),
            "architecture": str(self.config.get("architecture")),
            "dataset_version": self.config.get("dataset_version"),
            "trained_at": self.config.get("created_at"),
        }
        logger.info("Classification model loaded (%s, %d classes) on %s in %.0f ms",
                    self.info["architecture"], len(self.classes), self.device, self.load_time_ms)

    @torch.inference_mode()
    def predict(self, image: Image.Image) -> ClassificationResult:
        t0 = time.perf_counter()
        x = preprocess_image(image, self.config).to(self.device)
        t1 = time.perf_counter()
        probs = torch.softmax(self.model(x).float(), dim=1)[0].cpu()
        t2 = time.perf_counter()
        check_probabilities(probs, len(self.classes))
        k = int(torch.argmax(probs))
        cls = self.classes[k]
        return ClassificationResult(
            class_id=k, class_code=cls["code"], class_name=cls["name"], confidence=float(probs[k]),
            probabilities={c["name"]: float(probs[c["id"]]) for c in self.classes},
            preprocessing_ms=(t1 - t0) * 1000, model_ms=(t2 - t1) * 1000, imd_categories=list(cls.get("imd_categories", [])),
            wind_kt_range=list(cls["wind_kt"]) if cls.get("wind_kt") else None,
        )
