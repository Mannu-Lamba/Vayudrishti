"""Loads the ML models ONCE (FastAPI startup) and hands the loaded engines to the services.

Each engine validates its artifacts while loading: required files, checkpoint ↔ architecture (strict
state_dict), class mapping / feature list, and a load-time self-check of input → output shape. A model
that fails any of it is recorded (code + message, traceback in the log) instead of crashing the API:
/api/health and /api/ml/status report it and its endpoints answer 503 MODEL_NOT_LOADED.

Environment:
  ML_MODELS_DIR  directory holding identification/, classification/ and prediction/ (default: backend/models)
  ML_DEVICE      "cpu" or "cuda" (default: cuda when available)
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


@dataclass
class ModelSlot:
    key: str
    instance: Any | None = None
    error_code: str | None = None
    error_message: str | None = None
    loaded_at: str | None = None
    loading: bool = False

    @property
    def ready(self) -> bool:
        return self.instance is not None

    @property
    def state(self) -> str:
        """ready | loading | unavailable (not deployed / not loaded yet) | error (deployed but failed to load)."""
        if self.instance is not None:
            return "ready"
        if self.loading:
            return "loading"
        if self.error_code and self.error_code != "MODEL_FILE_MISSING":
            return "error"
        return "unavailable"


class MlRegistry:
    def __init__(self) -> None:
        self.identification = ModelSlot("identification")
        self.classification = ModelSlot("classification")
        self.prediction = ModelSlot("prediction")
        self._lock = threading.Lock()
        self._loaded = False

    def load(self, models_dir: Path | None = None, device: str | None = None, force: bool = False) -> None:
        from ml.classification.inference import ClassificationInference
        from ml.identification.inference import IdentificationInference
        from ml.prediction.inference import PredictionInference

        with self._lock:
            if self._loaded and not force:
                return
            base = Path(models_dir or os.environ.get("ML_MODELS_DIR") or DEFAULT_MODELS_DIR)
            device = device or os.environ.get("ML_DEVICE") or None
            engines = ((self.identification, IdentificationInference), (self.classification, ClassificationInference),
                       (self.prediction, PredictionInference))
            for slot, engine in engines:
                slot.instance, slot.error_code, slot.error_message, slot.loading = None, None, None, True
                try:
                    slot.instance = engine(base / slot.key, device)
                    slot.loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    info = slot.instance.info
                    logger.info("✅ %s model loaded: %s %s (%s) on %s", slot.key.capitalize(), info["name"], info["version"],
                                info["architecture"], slot.instance.device)
                except Exception as exc:  # recorded, never raised: the rest of the API must keep working
                    slot.error_code = getattr(exc, "code", "MODEL_LOAD_FAILED")
                    slot.error_message = getattr(exc, "message", str(exc))
                    log = logger.error if slot.error_code == "MODEL_FILE_MISSING" else logger.exception
                    log("❌ %s model unavailable (%s): %s", slot.key.capitalize(), slot.error_code, slot.error_message)
                finally:
                    slot.loading = False
            self._loaded = True


registry = MlRegistry()


def load_models() -> None:
    registry.load()
