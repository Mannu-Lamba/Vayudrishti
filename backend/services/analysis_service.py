"""Pipeline orchestration for POST /api/ml/analyze:

    image → identification → (only if CYCLONE) classification → (only if the storm's history supports one) track forecast

Stage 3 is never faked. A track forecast is computed from the storm's own observation history, which a single image
does not carry, so it runs only when the caller names the storm (`storm_id`, optional `timestamp`) and goes through
the same prediction service as POST /api/ml/predict. Otherwise `prediction.available` is false with a machine-readable
reason (NO_CYCLONE_DETECTED, STORM_ID_REQUIRED, INSUFFICIENT_HISTORY, MISSING_FEATURES, …).
"""

from __future__ import annotations

import logging
import time

from ml.imaging import ImageValidationError, decode_image, describe_image
from models.ml import AnalysisPrediction, AnalysisResponse, ClassificationSummary, ImageMetadata, InferenceTiming, InputCheck, ModelDescriptor
from services import classification_service, identification_service, prediction_service
from services.errors import MlServiceError

logger = logging.getLogger(__name__)


def _descriptor(info: dict) -> ModelDescriptor:
    return ModelDescriptor(name=info["name"], version=info["version"], architecture=info["architecture"])


def _prediction(detected: bool, metadata: ImageMetadata) -> AnalysisPrediction:
    if not detected:
        return AnalysisPrediction(available=False, reason="NO_CYCLONE_DETECTED",
                                  message="Identification found no cyclone, so no track forecast was run.")
    if not metadata.storm_id:
        return AnalysisPrediction(available=False, reason="STORM_ID_REQUIRED",
                                  message="A track forecast is computed from the storm's observation history, not from the image. "
                                          "Send storm_id (and the image's timestamp) to run it.")
    try:
        forecast = prediction_service.predict(metadata.storm_id, metadata.timestamp)
    except MlServiceError as exc:  # the stage is reported, not fatal: stages 1 and 2 already succeeded
        return AnalysisPrediction(available=False, reason=exc.code, message=exc.message)
    return AnalysisPrediction(available=True, forecast=forecast)


def analyze_upload(data: bytes | None, metadata: ImageMetadata, filename: str | None = None) -> AnalysisResponse:
    started = time.perf_counter()
    identifier = identification_service.engine()  # stage 1 is required
    classifier_slot = classification_service.registry.classification  # stage 2 is optional: reported, never faked
    try:
        image = decode_image(data)
    except ImageValidationError as exc:
        raise MlServiceError.from_validation(exc) from None
    input_check = InputCheck(**describe_image(image))  # descriptive: how far the image is from the training domain

    ident = identification_service.run_identifier(image)
    preprocessing_ms, model_ms = ident.preprocessing_ms, ident.model_ms
    classification, skipped = None, None
    if not ident.detected:
        skipped = "Identification found no cyclone, so intensity classification was not run."
    elif not classifier_slot.ready:
        skipped = "Classification model is not available."
    else:
        cls = classification_service.run_classifier(image)
        preprocessing_ms += cls.preprocessing_ms
        model_ms += cls.model_ms
        classification = ClassificationSummary(class_id=cls.class_id, class_name=cls.class_name, class_code=cls.class_code,
                                               confidence=cls.confidence, imd_categories=cls.imd_categories,
                                               wind_kt_range=cls.wind_kt_range, probabilities=cls.probabilities)

    prediction = _prediction(ident.detected, metadata)
    forecast = prediction.forecast
    if forecast is not None and not forecast.cached:
        preprocessing_ms += forecast.inference.preprocessing_ms
        model_ms += forecast.inference.model_ms

    models = {"identification": _descriptor(identifier.info)}
    if classifier_slot.ready:
        models["classification"] = _descriptor(classifier_slot.instance.info)
    if forecast is not None:
        models["prediction"] = ModelDescriptor(name=forecast.model.name, version=forecast.model.version, architecture=forecast.model.architecture)
    total_ms = (time.perf_counter() - started) * 1000
    logger.info("analyze %s → %s%s · forecast %s in %.1f ms", filename or "<upload>", ident.class_name,
                f" / {classification.class_code}" if classification else "", "attached" if forecast else prediction.reason, total_ms)
    return AnalysisResponse(
        identification=identification_service.to_schema(ident),
        classification=classification,
        classification_skipped_reason=skipped,
        prediction=prediction,
        input_check=input_check,
        metadata=metadata,
        models=models,
        inference=InferenceTiming(processing_time_ms=round(total_ms, 2), preprocessing_ms=round(preprocessing_ms, 2), model_ms=round(model_ms, 2)),
    )
