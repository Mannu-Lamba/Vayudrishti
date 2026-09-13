import type { PredictionConfidence, PredictionUncertainty } from "./prediction";

// ── Model / system status (future: GET /api/ml/status) ────────────────────

export type ModelStatus = "ready" | "processing" | "unavailable" | "not_connected" | "error";

export type SystemComponentKind = "model" | "service" | "dataset";

export interface SystemComponentStatus {
  id: string;
  label: string;
  kind: SystemComponentKind;
  status: ModelStatus;
  detail?: string;
  updatedAt?: string;
}

export type ModelTask = "detection" | "classification" | "track" | "intensity";

/** Model metadata (future: GET /api/ml/models). */
export interface ModelInfo {
  id: string;
  name: string;
  task: ModelTask;
  version: string;
  inputWindowHours?: number;
  forecastHorizonHours?: number;
  /** ISO date. */
  lastUpdated?: string;
  inputs?: string[];
  notes?: string;
}

/** GET /api/ml/status (backend/models/ml.py ModelRegistryResponse). Read from the model registry, never hardcoded. */
export interface ModelRegistry {
  /** ok when all three models are ready; degraded otherwise. */
  status?: "ok" | "degraded";
  components: SystemComponentStatus[];
  models: ModelInfo[];
  identification?: PredictionModelStatus;
  classification?: PredictionModelStatus;
  /** The track-prediction model behind POST /api/ml/predict. */
  prediction?: PredictionModelStatus;
}

/** A model's state in GET /api/ml/status. Never "ready" unless the checkpoint is loaded and self-checked on the backend. */
export type PredictionModelState = "ready" | "loading" | "unavailable" | "error";

export interface PredictionModelStatus {
  status: PredictionModelState;
  modelLoaded: boolean;
  modelName?: string | null;
  displayName?: string | null;
  modelVersion?: string | null;
  architecture?: string | null;
  trainedAt?: string | null;
  loadedAt?: string | null;
  /** cpu | cuda — where inference runs. */
  device?: string | null;
  /** MODEL_FILE_MISSING · MODEL_LOAD_FAILED · INVALID_MODEL_CONFIG · INVALID_CLASS_MAPPING · MODEL_SELF_CHECK_FAILED when not ready. */
  errorCode?: string | null;
  /** Operator-facing reason when not ready. */
  message?: string | null;
}

// ── ML inference contracts (POST /api/ml/*) ───────────────────────────────

export interface MlForecastStep {
  hours: number;
  latitude: number;
  longitude: number;
  /** km/h. */
  windSpeed: number;
  /** hPa. */
  pressure: number;
  /** 0–1; null/absent when the model produces no calibrated confidence. */
  confidence?: number | null;
  uncertaintyRadiusKm?: number | null;
  /** ISO 8601; derived from the observation time when absent. */
  forecastTime?: string;
  windSpeedKt?: number;
  /** Empirical [low, high] band, km/h. */
  windSpeedRange?: [number, number] | null;
  category?: string | null;
  /** Post-processing adjustments applied to this step (e.g. "wind_floored_at_zero"). */
  flags?: string[];
}

/**
 * POST /api/ml/predict body (backend/models/prediction.py PredictionRequest). The model forecasts from the
 * storm's observed history held by the server, so cycloneId + timestamp select the whole model input;
 * latitude/longitude only cross-check the position at T0 (400 POSITION_MISMATCH when > 50 km off).
 */
export interface PredictionRequest {
  /** IBTrACS storm id, e.g. 2020136N10088. */
  cycloneId: string;
  /** Forecast time T0, ISO 8601. Default: the storm's newest observation. */
  timestamp?: string;
  latitude?: number;
  longitude?: number;
  /** Subset of the model's lead times, e.g. [6, 12]. Default: all. */
  horizonsHours?: number[];
}

/** Core forecast payload shared by POST /api/ml/predict and GET /api/cyclones/{id}/prediction. */
export interface MlPredictResponse {
  cycloneId: string;
  issuedAt?: string;
  modelVersion?: string;
  forecast: MlForecastStep[];
}

/** Observed state at the forecast time T0, as the backend reports it. */
export interface PredictionCurrentState {
  observedAt: string;
  latitude: number;
  longitude: number;
  windKmh: number;
  windKt?: number;
  pressureHpa: number;
  category?: string | null;
  nature?: string | null;
  movementDirection?: string | null;
  movementSpeedKmh?: number | null;
}

export interface PredictionModelDescriptor {
  name: string;
  displayName: string;
  version: string;
  architecture: string;
  trainedAt?: string | null;
  datasetVersion?: string | null;
}

/** POST /api/ml/predict and GET /api/cyclones/{id}/prediction — one response model (backend/models/prediction.py PredictionResponse). */
export interface PredictionResourceResponse extends MlPredictResponse {
  confidence?: PredictionConfidence | null;
  uncertainty?: PredictionUncertainty | null;
  success?: boolean;
  status?: "success";
  name?: string;
  basin?: string;
  region?: string;
  subregion?: string;
  generatedAt?: string;
  model?: PredictionModelDescriptor;
  horizonsHours?: number[];
  input?: { historyWindowHours: number; observationIntervalHours: number; observationsUsed: number; windowStart: string; windowEnd: string; source?: string };
  current?: PredictionCurrentState;
  disclaimer?: string;
  cached?: boolean;
}

/** GET /api/cyclones/prediction-cases — held-out storms a forecast can be run for. */
export interface PredictionCase {
  cycloneId: string;
  name: string;
  season: number;
  basin: string;
  region: string;
  subregion: string;
  /** UI area id: a subregion, or the region when it has none (south_indian_ocean). */
  area: string;
  firstObservation: string;
  lastObservation: string;
  observations: number;
  peakWindKt: number | null;
  split?: string | null;
  /** Times a forecast can start from (complete 24 h history and observed wind + pressure). */
  forecastOrigins: string[];
}

export interface PredictionCasesResponse {
  cases: PredictionCase[];
  total: number;
  note: string;
}

/**
 * Detection / classification of a registry cyclone. The backend classifies uploaded images only (POST /api/ml/identify |
 * classify | analyze) and registry cyclones carry no image, so both are null until an image-backed endpoint exists.
 */
export interface MlAssessment {
  detection: { cycloneDetected: boolean; confidence: number } | null;
  classification: { category: string; confidence: number } | null;
}

// ── Image analysis (multipart upload: POST /api/ml/analyze | classify | identify) ──
// Snake_case mirrors the backend Pydantic models in backend/models/ml.py.

export interface MlModelDescriptor {
  name: string;
  version: string;
  architecture: string;
}

export interface ImageIdentification {
  detected: boolean;
  class_name: "CYCLONE" | "NO_CYCLONE";
  /** 0–1, probability of the predicted class (not calibrated). */
  confidence: number;
  cyclone_probability: number;
  probabilities: Record<string, number>;
}

export interface ImageClassification {
  class_id: number;
  class_name: string;
  class_code: string;
  confidence: number;
  imd_categories: string[];
  /** Class name → probability, sums to 1. */
  probabilities: Record<string, number>;
}

export interface ImageAnalysisMetadata {
  region?: string | null;
  basin?: string | null;
  storm_id?: string | null;
  timestamp?: string | null;
}

export interface InferenceTiming {
  processing_time_ms: number;
  preprocessing_ms: number;
  model_ms: number;
}

/** Stage 3 of POST /api/ml/analyze: a forecast from the storm's observation history (storm_id + timestamp), never from the image. */
export interface AnalysisPrediction {
  available: boolean;
  /** Why no forecast is attached: NO_CYCLONE_DETECTED · STORM_ID_REQUIRED · INSUFFICIENT_HISTORY · MISSING_FEATURES · … */
  reason: string | null;
  message: string | null;
  /** The same object POST /api/ml/predict returns. */
  forecast: PredictionResourceResponse | null;
}

/** POST /api/ml/analyze — identification, classification when a cyclone is detected, track forecast when the history allows. */
export interface ImageAnalysisResponse {
  success: true;
  identification: ImageIdentification;
  classification: ImageClassification | null;
  classification_skipped_reason: string | null;
  prediction: AnalysisPrediction;
  metadata: ImageAnalysisMetadata;
  models: Record<string, MlModelDescriptor>;
  inference: InferenceTiming;
}

/** POST /api/ml/classify */
export interface ImageClassifyResponse {
  success: true;
  model: MlModelDescriptor;
  prediction: Omit<ImageClassification, "probabilities">;
  probabilities: Record<string, number>;
  metadata: ImageAnalysisMetadata;
  inference: InferenceTiming;
}

/** POST /api/ml/identify */
export interface ImageIdentifyResponse {
  success: true;
  model: MlModelDescriptor;
  identification: ImageIdentification;
  metadata: ImageAnalysisMetadata;
  inference: InferenceTiming;
}

/** Error body of every /api/ml endpoint. */
export interface MlErrorBody {
  success: false;
  status?: "error";
  error: { code: string; message: string };
}
