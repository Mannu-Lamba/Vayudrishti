"""PredictionInference — load once, forecast many.

Loads backend/models/prediction/{best_model.pth, model_config.json}; the config carries the temporal
window, feature list, normalisation statistics and (optional) empirical uncertainty radii the model
was trained and evaluated with. predict() runs: origin lookup → input window → normalisation →
model (eval, no_grad) → de-normalisation → post-processing.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ml.architecture import self_check
from ml.prediction.config import SequenceConfig
from ml.prediction.features import FEATURE_NAMES, Normalizer
from ml.prediction.model import build_model
from ml.prediction.postprocess import ForecastStep, postprocess
from ml.prediction.sequences import SequenceInputError, build_inference_window, missing_required_features, resolve_origin

logger = logging.getLogger(__name__)
REQUIRED_FILES = ("best_model.pth", "model_config.json")


class PredictionArtifactsError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PredictionResult:
    storm_id: str
    origin: pd.Timestamp
    anchor: dict
    steps: list[ForecastStep]
    observations_used: int
    window_start: pd.Timestamp
    preprocessing_ms: float
    model_ms: float


class PredictionInference:
    NAME = "cyclone-track-prediction"

    def __init__(self, model_dir: Path, device: str | None = None):
        started = time.perf_counter()
        model_dir = Path(model_dir)
        missing = [name for name in REQUIRED_FILES if not (model_dir / name).exists()]
        if missing:
            raise PredictionArtifactsError("MODEL_FILE_MISSING", f"Prediction model files missing in {model_dir}: {', '.join(missing)}")
        self.config = json.loads((model_dir / "model_config.json").read_text(encoding="utf-8"))
        if self.config.get("features") != FEATURE_NAMES:
            raise PredictionArtifactsError("INVALID_MODEL_CONFIG", "model_config.json features differ from the serving feature pipeline")
        self.cfg = SequenceConfig.from_dict(self.config["sequence"])
        self.normalizer = Normalizer.from_dict(self.config["normalization"])
        self.uncertainty = self.config.get("uncertainty")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        try:
            ckpt = torch.load(model_dir / "best_model.pth", map_location=self.device, weights_only=True)
            self.model = build_model(ckpt["model_spec"])
            self.model.load_state_dict(ckpt["state_dict"], strict=True)
        except Exception as exc:
            raise PredictionArtifactsError("MODEL_LOAD_FAILED", f"Could not load the prediction checkpoint: {exc}") from exc
        self.model.to(self.device).eval()
        spec = ckpt["model_spec"]
        expected = {"n_features": len(FEATURE_NAMES), "n_steps": self.cfg.steps, "n_horizons": len(self.cfg.horizons_hours)}
        wrong = {key: spec.get(key) for key, value in expected.items() if spec.get(key) != value}
        if wrong:
            raise PredictionArtifactsError("INVALID_MODEL_CONFIG", f"Checkpoint model_spec {wrong} disagrees with model_config.json {expected}")
        horizons = len(self.cfg.horizons_hours)
        try:  # the exact serving path on a probe input: normalise → network → de-normalise
            probe = self.normalizer.transform(np.zeros((1, self.cfg.steps, len(FEATURE_NAMES)), dtype=np.float32))
            self_check(self.model, tuple(probe.shape), (1, horizons, 4), self.device)
            if self.normalizer.denormalize_targets(np.zeros((horizons, 4), dtype=np.float32)).shape != (horizons, 4):
                raise ValueError("target de-normalisation does not return one row per horizon")
        except Exception as exc:
            raise PredictionArtifactsError("MODEL_SELF_CHECK_FAILED", f"The prediction model failed its load-time check: {exc}") from exc
        self.load_time_ms = (time.perf_counter() - started) * 1000
        self.info = {
            "name": self.NAME,
            "display_name": self.config.get("display_name", "VayuDrishti Track Prediction Model"),
            "version": str(self.config.get("model_version", "v1")),
            "architecture": str(ckpt["model_spec"].get("architecture")),
            "dataset_version": self.config.get("dataset_version"),
            "trained_at": self.config.get("created_at"),
            "horizons_hours": list(self.cfg.horizons_hours),
            "history_window_hours": self.cfg.history_window_hours,
        }
        logger.info("Prediction model loaded (%s, horizons %s h) on %s in %.0f ms",
                    self.info["architecture"], self.info["horizons_hours"], self.device, self.load_time_ms)

    @torch.inference_mode()
    def predict(self, storm: pd.DataFrame, at: pd.Timestamp | None = None) -> PredictionResult:
        """storm: one validated, time-sorted storm (repository output). Raises SequenceInputError for
        unusable input and PostprocessingError for implausible output."""
        t0 = time.perf_counter()
        end = resolve_origin(storm, at, self.cfg)
        window, anchor = build_inference_window(storm, end, self.cfg)
        missing = missing_required_features(storm, end, self.cfg)
        if missing:
            raise SequenceInputError(
                "MISSING_FEATURES",
                f"The model needs {' and '.join(missing)} for every observation in the {self.cfg.history_window_hours} h input "
                "window; this cyclone's record does not provide them, and they are never filled in.")
        if not (np.isfinite(anchor["wind0"]) and np.isfinite(anchor["pres0"])):
            raise SequenceInputError(
                "MISSING_CURRENT_INTENSITY",
                "The wind speed or central pressure was not observed at this time, so no intensity/pressure forecast can start from it.")
        x = torch.from_numpy(self.normalizer.transform(window[None])).to(self.device)
        t1 = time.perf_counter()
        z = self.model(x)[0].float().cpu().numpy()
        t2 = time.perf_counter()
        deltas = self.normalizer.denormalize_targets(z)
        steps = postprocess(anchor, deltas, self.cfg, self.uncertainty)
        return PredictionResult(
            storm_id=str(anchor["storm_id"]), origin=anchor["t0"], anchor=anchor, steps=steps,
            observations_used=self.cfg.steps, window_start=storm["time"].iloc[end - self.cfg.steps + 1],
            preprocessing_ms=(t1 - t0) * 1000, model_ms=(t2 - t1) * 1000,
        )
