"""ML endpoints (mounted at /api/ml). Router → Pydantic schema → service → model registry → PyTorch model.

Handlers are sync `def`, so FastAPI runs each inference in its threadpool without blocking the
event loop. Every error follows {success: false, status: "error", error: {code, message}} — no stack traces.
"""

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from models.ml import (
    AnalysisResponse, ClassificationResponse, ErrorDetail, ErrorResponse, IdentificationResponse, ImageMetadata, ModelInfo,
    ModelRegistryResponse, ModelStatus, SystemComponentStatus,
)
from models.prediction import PredictionRequest, PredictionResponse
from services import analysis_service, classification_service, identification_service, prediction_service
from services.errors import MlServiceError
from repositories.cyclone_repository import mongo_repository, repository
from services.ml_registry import registry

router = APIRouter(tags=["ml"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "No file, empty, corrupted or wrongly sized image"},
    413: {"model": ErrorResponse, "description": "Image larger than 10 MB"},
    415: {"model": ErrorResponse, "description": "Not a supported image type"},
    500: {"model": ErrorResponse, "description": "Preprocessing or inference failed"},
    503: {"model": ErrorResponse, "description": "Model not loaded"},
}
FILE_FIELD = File(None, description="Satellite IR image (PNG/JPEG/TIFF/BMP/WebP), e.g. a GridSat-style 18°×18° crop")


def _error(exc: MlServiceError) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


def _metadata(region, basin, storm_id, timestamp) -> ImageMetadata:
    return ImageMetadata(region=region or None, basin=basin or None, storm_id=storm_id or None, timestamp=timestamp or None)


def _read(file: UploadFile | None) -> bytes | None:
    return file.file.read() if file is not None else None


@router.post("/classify", response_model=ClassificationResponse, responses=ERROR_RESPONSES,
             summary="Classify a cyclone image into an IMD intensity class")
def classify(file: UploadFile | None = FILE_FIELD, region: str | None = Form(None), basin: str | None = Form(None),
             storm_id: str | None = Form(None), timestamp: str | None = Form(None)):
    """Stage 2 only. Assumes the image contains a cyclone — use /api/ml/analyze for the gated pipeline."""
    try:
        return classification_service.classify_upload(_read(file), _metadata(region, basin, storm_id, timestamp), file.filename if file else None)
    except MlServiceError as exc:
        return _error(exc)


@router.post("/identify", response_model=IdentificationResponse, responses=ERROR_RESPONSES,
             summary="Is there a tropical cyclone in this image?")
def identify(file: UploadFile | None = FILE_FIELD, region: str | None = Form(None), basin: str | None = Form(None),
             storm_id: str | None = Form(None), timestamp: str | None = Form(None)):
    try:
        return identification_service.identify_upload(_read(file), _metadata(region, basin, storm_id, timestamp), file.filename if file else None)
    except MlServiceError as exc:
        return _error(exc)


@router.post("/analyze", response_model=AnalysisResponse, responses=ERROR_RESPONSES,
             summary="Identification → classification → track forecast pipeline")
def analyze(file: UploadFile | None = FILE_FIELD, region: str | None = Form(None), basin: str | None = Form(None),
            storm_id: str | None = Form(None, description="Storm the image shows (IBTrACS SID or cyclone_database id): enables stage 3"),
            timestamp: str | None = Form(None, description="Image time, ISO 8601: the forecast starts from the latest fix at or up to 3 h before it")):
    """1. Identification (always). 2. Classification — only when a cyclone is detected. 3. Track forecast — only when a
    cyclone is detected **and** `storm_id` names a storm whose observation history supports one; it is computed from that
    history by the same service as POST /api/ml/predict, never from the image. Otherwise `prediction.available` is false
    with a reason (NO_CYCLONE_DETECTED, STORM_ID_REQUIRED, INSUFFICIENT_HISTORY, MISSING_FEATURES, …) — never a fake forecast.
    Errors from the image itself (400/413/415) or a missing identification model (503) fail the whole request."""
    try:
        return analysis_service.analyze_upload(_read(file), _metadata(region, basin, storm_id, timestamp), file.filename if file else None)
    except MlServiceError as exc:
        return _error(exc)


PREDICT_RESPONSES = {
    400: {"model": ErrorResponse, "description": "INVALID_CYCLONE_ID · UNSUPPORTED_HORIZON · POSITION_MISMATCH"},
    404: {"model": ErrorResponse, "description": "CYCLONE_NOT_FOUND · OBSERVATION_NOT_FOUND (no fix at or up to 3 h before `timestamp`)"},
    422: {"model": ErrorResponse, "description": "VALIDATION_ERROR (malformed body) · INSUFFICIENT_HISTORY (fewer than 5 regular fixes in the "
                                                 "previous 24 h) · MISSING_CURRENT_INTENSITY (wind or pressure not observed at T0)"},
    500: {"model": ErrorResponse, "description": "INFERENCE_FAILED · PREDICTION_OUT_OF_RANGE / INVALID_MODEL_OUTPUT (post-processing rejected the output)"},
    503: {"model": ErrorResponse, "description": "MODEL_NOT_LOADED · DATA_UNAVAILABLE"},
}


@router.post("/predict", response_model=PredictionResponse, responses=PREDICT_RESPONSES,
             summary="Forecast a cyclone's track, wind and pressure at T+6 … T+24 h")
def predict_cyclone(request: PredictionRequest):
    """Runs the already-loaded track-prediction model (GRU) on the storm's observed best-track history ending at
    `timestamp`: router → `PredictionRequest` → prediction service → model registry → model. Same result and
    cache as `GET /api/cyclones/{id}/prediction`.

    `confidence` is always null (no calibrated confidence is produced). `uncertaintyRadiusKm` is an empirical
    radius from validation errors, not a calibrated probability. AI-assisted decision support, not an official forecast."""
    try:
        return prediction_service.predict_request(request)
    except MlServiceError as exc:
        return _error(exc)


LOAD_FAILURE_COPY = {  # operator-facing; the full error (with server paths) stays in the backend log
    "MODEL_FILE_MISSING": "Model files are not deployed on the server",
    "MODEL_LOAD_FAILED": "Model failed to load",
    "INVALID_CLASS_MAPPING": "Model metadata is inconsistent",
    "INVALID_MODEL_CONFIG": "Model metadata is inconsistent",
    "MODEL_SELF_CHECK_FAILED": "Model failed its load-time self-check",
}
COMPONENT_STATUS = {"ready": "ready", "loading": "processing", "unavailable": "unavailable", "error": "error"}


def _component(slot, label: str) -> SystemComponentStatus:
    if slot.ready:
        return SystemComponentStatus(id=f"{slot.key}-model", label=label, kind="model", status="ready",
                                     detail=f"{slot.instance.info['architecture']} · {slot.instance.info['version']}", updatedAt=slot.loaded_at)
    detail = "Loading" if slot.state == "loading" else LOAD_FAILURE_COPY.get(slot.error_code or "", "Model not loaded")
    return SystemComponentStatus(id=f"{slot.key}-model", label=label, kind="model", status=COMPONENT_STATUS[slot.state], detail=detail)


def _model_status(slot, label: str) -> ModelStatus:
    if slot.ready:
        engine = slot.instance
        info = engine.info
        return ModelStatus(status="ready", modelLoaded=True, modelName=info["name"], displayName=info.get("display_name") or label,
                           modelVersion=info["version"], architecture=info["architecture"], trainedAt=info.get("trained_at"),
                           loadedAt=slot.loaded_at, device=str(engine.device))
    state = slot.state
    message = f"The {slot.key} model is loading." if state == "loading" else f"{LOAD_FAILURE_COPY.get(slot.error_code or '', 'Model not loaded')}."
    return ModelStatus(status=state, modelLoaded=False, errorCode=slot.error_code, message=message)


@router.get("/status", response_model=ModelRegistryResponse, summary="Readiness and metadata of the three models")
def status():
    """Read from the model registry on every call, never hardcoded. `identification`, `classification` and
    `prediction` each report ready · loading · unavailable (files not deployed) · error (load or self-check
    failed); a model is "ready" only when its checkpoint is in memory and passed the load-time check.
    `status` is ok when all three are ready, otherwise degraded."""
    statuses = {
        "identification": _model_status(registry.identification, "Cyclone identification model"),
        "classification": _model_status(registry.classification, "IMD intensity classification model"),
        "prediction": _model_status(registry.prediction, "Track prediction model"),
    }
    components = [
        _component(registry.identification, "Identification model"),
        _component(registry.classification, "Classification model"),
        _component(registry.prediction, "Track prediction model"),
        SystemComponentStatus(id="cyclone-observations", label="Cyclone observations (IBTrACS)", kind="dataset",
                              status="ready" if repository.ready else "unavailable",
                              detail=f"{len(repository.list_storms())} held-out storms" if repository.ready else "Observation table not loaded"),
        SystemComponentStatus(id="cyclone-database", label="Cyclone database (MongoDB)", kind="dataset",
                              status="ready" if mongo_repository.connected else "unavailable",
                              detail=mongo_repository.status_detail()),
    ]
    models = []
    for slot, task, name, notes in (
        (registry.identification, "detection", "Cyclone identification", "Binary CYCLONE / NO_CYCLONE on an 18°×18° IR scene"),
        (registry.classification, "classification", "IMD intensity classification",
         "4 IMD groups: D/DD · CS/SCS · VSCS · ESCS/SuCS (labels from IBTrACS USA_WIND)"),
    ):
        if slot.ready:
            info = slot.instance.info
            models.append(ModelInfo(id=info["name"], name=name, task=task, version=info["version"], lastUpdated=info.get("trained_at"),
                                    inputs=["GridSat-B1 IR (~11 µm) image"], notes=notes))
    if registry.prediction.ready:
        info = registry.prediction.instance.info
        models.append(ModelInfo(
            id=info["name"], name=info["display_name"], task="track", version=info["version"], lastUpdated=info.get("trained_at"),
            inputWindowHours=info["history_window_hours"], forecastHorizonHours=max(info["horizons_hours"]),
            inputs=["IBTrACS best-track position, 1-min wind, central pressure, motion, distance to land"],
            notes=f"{info['architecture'].upper()} multi-task forecast of track, wind and pressure at T+{', '.join(map(str, info['horizons_hours']))} h"))
    overall = "ok" if all(s.status == "ready" for s in statuses.values()) else "degraded"
    return ModelRegistryResponse(status=overall, components=components, models=models, **statuses)
