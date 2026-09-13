"""Classification service: validate the upload → run the loaded classifier → typed response.

Routers call only this module; they never see the network, tensors or checkpoint files.
"""

from __future__ import annotations

import logging
import time

from ml.architecture import ModelOutputError
from ml.classification.preprocessing import PreprocessingError
from ml.imaging import ImageValidationError, decode_image
from models.ml import ClassificationPrediction, ClassificationResponse, ImageMetadata, InferenceTiming, ModelDescriptor
from services.errors import MODEL_NOT_LOADED_MESSAGES, MlServiceError
from services.ml_registry import registry

logger = logging.getLogger(__name__)


def engine():
    """The loaded ClassificationInference, or MlServiceError 503 MODEL_NOT_LOADED."""
    slot = registry.classification
    if not slot.ready:
        raise MlServiceError("MODEL_NOT_LOADED", MODEL_NOT_LOADED_MESSAGES["classification"], 503)
    return slot.instance


def run_classifier(image):
    """Run the classifier on a decoded PIL image; maps failures to service errors."""
    try:
        return engine().predict(image)
    except MlServiceError:
        raise
    except PreprocessingError:
        logger.exception("Classification preprocessing failed")
        raise MlServiceError("PREPROCESSING_FAILED", "The image could not be prepared for the classification model.", 500) from None
    except ModelOutputError as exc:
        logger.error("Classification output rejected: %s", exc.message)
        raise MlServiceError(exc.code, "The classification model returned an invalid result for this image, so none is shown.", 500) from None
    except Exception:
        logger.exception("Classification inference failed")
        raise MlServiceError("INFERENCE_FAILED", "The classification model could not process this image.", 500) from None


def classify_upload(data: bytes | None, metadata: ImageMetadata, filename: str | None = None) -> ClassificationResponse:
    started = time.perf_counter()
    classifier = engine()  # fail fast before decoding when the model is missing
    try:
        image = decode_image(data)
    except ImageValidationError as exc:
        raise MlServiceError.from_validation(exc) from None
    result = run_classifier(image)
    total_ms = (time.perf_counter() - started) * 1000
    logger.info("classify %s → %s (%.3f) in %.1f ms [model %.1f ms]", filename or "<upload>", result.class_code, result.confidence, total_ms, result.model_ms)
    return ClassificationResponse(
        model=ModelDescriptor(name=classifier.info["name"], version=classifier.info["version"], architecture=classifier.info["architecture"]),
        prediction=ClassificationPrediction(class_id=result.class_id, class_name=result.class_name, class_code=result.class_code,
                                            confidence=result.confidence, imd_categories=result.imd_categories,
                                            wind_kt_range=result.wind_kt_range),
        probabilities=result.probabilities,
        metadata=metadata,
        inference=InferenceTiming(processing_time_ms=round(total_ms, 2), preprocessing_ms=round(result.preprocessing_ms, 2), model_ms=round(result.model_ms, 2)),
    )
