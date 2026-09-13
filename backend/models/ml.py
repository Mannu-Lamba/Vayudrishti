"""Pydantic contracts for the ML endpoints (/api/ml/*) and /api/health.

The frontend mirrors these by hand in frontend/src/types/model.ts — keep the two in sync.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.prediction import PredictionResponse


class _Model(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ModelDescriptor(_Model):
    name: str = Field(examples=["cyclone-classification"])
    version: str = Field(examples=["v1"])
    architecture: str = Field(examples=["efficientnet_b0"])


class ImageMetadata(_Model):
    """Optional context the caller sends with the image; echoed back, never inferred."""
    region: str | None = None
    basin: str | None = None
    storm_id: str | None = None
    timestamp: str | None = None


class InferenceTiming(_Model):
    processing_time_ms: float = Field(description="Total server time for the request (decode + preprocess + model)")
    preprocessing_ms: float
    model_ms: float


class ClassificationPrediction(_Model):
    class_id: int
    class_name: str = Field(examples=["Very Severe Cyclonic Storm"])
    class_code: str = Field(examples=["VSCS"])
    confidence: float = Field(ge=0, le=1, description="Probability of the predicted class (max softmax); not calibrated")
    imd_categories: list[str] = Field(default_factory=list, description="IMD categories covered by the predicted class")
    wind_kt_range: list[float | None] | None = Field(None, examples=[[64, 89]], description="Sustained-wind range (kt, 1-min) that DEFINES "
                                                     "the predicted class in class_mapping.json; not a wind estimate. null upper bound = open")


class InputWarning(_Model):
    code: Literal["COLOUR_IMAGE", "NOT_SQUARE", "LOW_RESOLUTION", "LOW_CONTRAST"]
    message: str


class InputCheck(_Model):
    """How the uploaded image compares with the training domain (GridSat-B1 IR ~11 µm, single channel, square ~18°×18°,
    256 px). Descriptive only: the prediction is unchanged, the warnings say how far to trust it."""
    format: str | None
    width: int
    height: int
    mode: str
    colour_fraction: float = Field(description="Share of pixels with visible colour (HSV saturation > 0.15)")
    contrast: float = Field(description="Standard deviation of the grey image, 0–1")
    in_training_domain: bool
    warnings: list[InputWarning]


class ClassificationResponse(_Model):
    success: Literal[True] = True
    model: ModelDescriptor
    prediction: ClassificationPrediction
    probabilities: dict[str, float] = Field(description="Class name → probability; sums to 1")
    metadata: ImageMetadata
    inference: InferenceTiming


class IdentificationResult(_Model):
    detected: bool
    class_name: Literal["CYCLONE", "NO_CYCLONE"]
    confidence: float = Field(ge=0, le=1)
    cyclone_probability: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class IdentificationResponse(_Model):
    success: Literal[True] = True
    model: ModelDescriptor
    identification: IdentificationResult
    metadata: ImageMetadata
    inference: InferenceTiming


class ClassificationSummary(_Model):
    class_id: int
    class_name: str
    class_code: str
    confidence: float = Field(ge=0, le=1)
    imd_categories: list[str] = Field(default_factory=list)
    wind_kt_range: list[float | None] | None = None
    probabilities: dict[str, float]


class AnalysisPrediction(_Model):
    """Stage 3 of /api/ml/analyze. A forecast is attached only when the named storm's observation history supports one."""
    available: bool
    reason: str | None = Field(
        None, examples=["INSUFFICIENT_HISTORY"],
        description="Why no forecast is attached: NO_CYCLONE_DETECTED · STORM_ID_REQUIRED · or the code POST /api/ml/predict "
                    "would return (INSUFFICIENT_HISTORY, MISSING_FEATURES, MISSING_CURRENT_INTENSITY, CYCLONE_NOT_FOUND, "
                    "OBSERVATION_NOT_FOUND, INVALID_CYCLONE_ID, INVALID_TIME, MODEL_NOT_LOADED, DATABASE_UNAVAILABLE, …)")
    message: str | None = None
    forecast: PredictionResponse | None = Field(None, description="The same object POST /api/ml/predict returns (camelCase keys)")


class AnalysisResponse(_Model):
    success: Literal[True] = True
    identification: IdentificationResult
    classification: ClassificationSummary | None = Field(description="null when identification found no cyclone")
    classification_skipped_reason: str | None = None
    prediction: AnalysisPrediction = Field(description="Track forecast from the storm's observation history (storm_id + timestamp), "
                                                       "never from the image; available=false with a reason when none can be made")
    input_check: InputCheck
    metadata: ImageMetadata
    models: dict[str, ModelDescriptor]
    inference: InferenceTiming


class ErrorDetail(_Model):
    code: str = Field(examples=["MODEL_NOT_LOADED"])
    message: str = Field(examples=["Classification model is not available."])


class ErrorResponse(_Model):
    success: Literal[False] = False
    status: Literal["error"] = "error"
    error: ErrorDetail


class HealthServices(_Model):
    api: bool
    identification_model: bool
    classification_model: bool
    prediction_model: bool


class HealthResponse(_Model):
    status: Literal["ok", "degraded"] = Field(description="'degraded' when a deployed model failed to load; the API itself is up")
    version: str
    timestamp: str
    services: HealthServices


# GET /api/ml/status — shape of frontend/src/types/model.ts ModelRegistry
class SystemComponentStatus(_Model):
    id: str
    label: str
    kind: Literal["model", "service", "dataset"]
    status: Literal["ready", "processing", "unavailable", "not_connected", "error"]
    detail: str | None = None
    updatedAt: str | None = None


class ModelInfo(_Model):
    id: str
    name: str
    task: Literal["detection", "classification", "track", "intensity"]
    version: str
    inputWindowHours: int | None = None
    forecastHorizonHours: int | None = None
    lastUpdated: str | None = None
    inputs: list[str] | None = None
    notes: str | None = None


class ModelStatus(_Model):
    """One model in the registry, as the frontend's status badges show it. Read from the registry, never hardcoded."""
    status: Literal["ready", "loading", "unavailable", "error"] = Field(
        description="ready = loaded, self-checked and serving · loading = startup load in progress · unavailable = model files "
                    "not deployed · error = files present but loading or the load-time self-check failed")
    modelLoaded: bool
    modelName: str | None = Field(None, examples=["cyclone-track-prediction"])
    displayName: str | None = Field(None, examples=["VayuDrishti Track Prediction Model"])
    modelVersion: str | None = Field(None, examples=["v1"])
    architecture: str | None = Field(None, examples=["gru"])
    trainedAt: str | None = None
    loadedAt: str | None = None
    device: str | None = Field(None, examples=["cpu"], description="Where inference runs (cuda when available, else cpu)")
    errorCode: str | None = Field(None, description="Load failure code when not ready (MODEL_FILE_MISSING, MODEL_LOAD_FAILED, "
                                                    "INVALID_MODEL_CONFIG, INVALID_CLASS_MAPPING, MODEL_SELF_CHECK_FAILED)")
    message: str | None = Field(None, description="Operator-facing reason when not ready; never a server path or traceback")


PredictionModelStatus = ModelStatus  # the Phase 5 name, kept for imports


class ModelRegistryResponse(_Model):
    status: Literal["ok", "degraded"] = Field(description="ok when all three models are ready; degraded otherwise (the API itself is up)")
    components: list[SystemComponentStatus]
    models: list[ModelInfo] = Field(description="Metadata of the models that are loaded")
    identification: ModelStatus
    classification: ModelStatus
    prediction: ModelStatus
