"""Identification service (stage 1): validated upload → CYCLONE / NO_CYCLONE."""

from __future__ import annotations

import logging
import time

from ml.architecture import ModelOutputError
from ml.classification.preprocessing import PreprocessingError
from ml.imaging import ImageValidationError, decode_image
from models.ml import IdentificationResponse, IdentificationResult, ImageMetadata, InferenceTiming, ModelDescriptor
from services.errors import MODEL_NOT_LOADED_MESSAGES, MlServiceError
from services.ml_registry import registry

logger = logging.getLogger(__name__)


def engine():
    slot = registry.identification
    if not slot.ready:
        raise MlServiceError("MODEL_NOT_LOADED", MODEL_NOT_LOADED_MESSAGES["identification"], 503)
    return slot.instance


def run_identifier(image):
    try:
        return engine().predict(image)
    except MlServiceError:
        raise
    except PreprocessingError:
        logger.exception("Identification preprocessing failed")
        raise MlServiceError("PREPROCESSING_FAILED", "The image could not be prepared for the identification model.", 500) from None
    except ModelOutputError as exc:
        logger.error("Identification output rejected: %s", exc.message)
        raise MlServiceError(exc.code, "The identification model returned an invalid result for this image, so none is shown.", 500) from None
    except Exception:
        logger.exception("Identification inference failed")
        raise MlServiceError("INFERENCE_FAILED", "The identification model could not process this image.", 500) from None


def to_schema(result) -> IdentificationResult:
    return IdentificationResult(detected=result.detected, class_name=result.class_name, confidence=result.confidence,
                                cyclone_probability=result.cyclone_probability, probabilities=result.probabilities)


def identify_upload(data: bytes | None, metadata: ImageMetadata, filename: str | None = None) -> IdentificationResponse:
    started = time.perf_counter()
    identifier = engine()
    try:
        image = decode_image(data)
    except ImageValidationError as exc:
        raise MlServiceError.from_validation(exc) from None
    result = run_identifier(image)
    total_ms = (time.perf_counter() - started) * 1000
    logger.info("identify %s → %s (p=%.3f) in %.1f ms", filename or "<upload>", result.class_name, result.cyclone_probability, total_ms)
    return IdentificationResponse(
        model=ModelDescriptor(name=identifier.info["name"], version=identifier.info["version"], architecture=identifier.info["architecture"]),
        identification=to_schema(result),
        metadata=metadata,
        inference=InferenceTiming(processing_time_ms=round(total_ms, 2), preprocessing_ms=round(result.preprocessing_ms, 2), model_ms=round(result.model_ms, 2)),
    )
