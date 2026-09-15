// AI prediction, ML inference and model status. Components never see which HTTP shape the backend
// chose: both GET /api/cyclones/{id}/prediction and POST /api/ml/predict are normalised into
// CyclonePrediction here.
//
// Every function here calls the live backend, in demo mode too: forecasts, classifications and model
// status can only come from the trained models, so there is deliberately no mock or demo fallback.
import { environment } from "@/config/environment";
import { ApiError, apiGet, apiRequest, checkApiHealth, orNullOn404 } from "./apiClient";
import { getCycloneById } from "./cycloneApi";
import type { DateRangeQuery, ServiceResult } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";
import type {
  ImageAnalysisMetadata, ImageAnalysisResponse, ImageClassifyResponse, ImageIdentifyResponse, MlAssessment, ModelRegistry,
  PredictionCasesResponse, PredictionCurrentState, PredictionModelState, PredictionModelStatus, PredictionRequest, PredictionResourceResponse,
} from "@/types/model";
import type { CyclonePrediction, IntensityPrediction, PredictionAnchor, TrackPrediction } from "@/types/prediction";
import type { CycloneTrackResponse } from "@/types/track";
import { toIsoTimestamp } from "@/lib/time";

/** Horizons requested today. Adding 36 / 48 / 72 needs no component change. */
export const DEFAULT_HORIZONS_HOURS = [6, 12, 18, 24];
const pad = (value: number) => String(value).padStart(2, "0");
const enc = encodeURIComponent;
const live = <T,>(data: T): ServiceResult<T> => ({ data, source: "live" });

/** Scores may arrive as 0–1 or as percentages; the UI always works in 0–1. */
const unit = (value: number | undefined) => (value == null ? undefined : value > 1 ? value / 100 : value);

/** The registry's latest fix as a forecast anchor — only when wind and pressure were observed there. */
function anchorFrom(cyclone: CycloneData): PredictionAnchor | null {
  if (cyclone.windKmh == null || cyclone.pressureHpa == null) return null;
  return {
    observedAt: toIsoTimestamp(cyclone.observedAt),
    latitude: cyclone.location.latitude,
    longitude: cyclone.location.longitude,
    windKmh: cyclone.windKmh,
    pressureHpa: cyclone.pressureHpa,
    category: cyclone.category ?? "",
    movementDirection: cyclone.movementDirection ?? undefined,
    movementSpeedKmh: cyclone.movementSpeedKmh ?? undefined,
  };
}

/** The observed state the backend anchored a forecast on (live track model). */
function anchorFromCurrent(current: PredictionCurrentState): PredictionAnchor {
  return {
    observedAt: current.observedAt,
    latitude: current.latitude,
    longitude: current.longitude,
    windKmh: current.windKmh,
    pressureHpa: current.pressureHpa,
    category: current.category ?? "",
    movementDirection: current.movementDirection ?? undefined,
    movementSpeedKmh: current.movementSpeedKmh ?? undefined,
  };
}

/** Adapter shared by demo and live responses. A missing confidence stays missing — it is never shown as 0 %. */
export function normalizePrediction(response: PredictionResourceResponse, anchor: PredictionAnchor, cycloneId: string): CyclonePrediction {
  const observedMs = Date.parse(anchor.observedAt);
  const forecast = [...response.forecast]
    .sort((a, b) => a.hours - b.hours)
    .map((step) => ({
      id: `${cycloneId}-f${pad(step.hours)}`,
      hours: step.hours,
      label: `T+${step.hours}h`,
      forecastTime: step.forecastTime ?? (Number.isFinite(observedMs) ? new Date(observedMs + step.hours * 3_600_000).toISOString() : anchor.observedAt),
      latitude: step.latitude,
      longitude: step.longitude,
      windKmh: step.windSpeed,
      pressureHpa: step.pressure,
      confidence: unit(step.confidence ?? undefined),
      uncertaintyRadiusKm: step.uncertaintyRadiusKm ?? undefined,
      windRangeKmh: step.windSpeedRange ?? undefined,
      category: step.category ?? undefined,
    }));
  const scores = forecast.map((point) => point.confidence).filter((value): value is number => value != null);
  const meanConfidence = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : undefined;
  const confidence = response.confidence ?? {};
  return {
    cycloneId,
    issuedAt: response.issuedAt ?? anchor.observedAt,
    modelVersion: response.modelVersion,
    current: anchor,
    forecast,
    confidence: {
      track: unit(confidence.track) ?? meanConfidence,
      intensity: unit(confidence.intensity),
      classification: unit(confidence.classification),
      detection: unit(confidence.detection),
    },
    uncertainty: response.uncertainty ?? (forecast.some((point) => point.uncertaintyRadiusKm) ? { method: "model" } : undefined),
    generatedAt: response.generatedAt,
    disclaimer: response.disclaimer,
  };
}

function fetchLivePrediction(cycloneId: string): Promise<PredictionResourceResponse | null> {
  if (environment.predictionStrategy === "inference") {
    const request: PredictionRequest = { cycloneId, horizonsHours: DEFAULT_HORIZONS_HOURS };
    return orNullOn404(apiRequest<PredictionResourceResponse>("/ml/predict", { method: "POST", body: request }));
  }
  return orNullOn404(apiGet<PredictionResourceResponse>(`/cyclones/${enc(cycloneId)}/prediction`));
}

/** The model cannot forecast this cyclone (unknown storm, too little history, missing inputs) — "no prediction", not a failure. */
const NO_FORECAST_STATUSES = [400, 404, 422];
/** Ids the prediction service can look up: IBTrACS SIDs and cyclone_database sample ids. Others (demo registry ids) have no history on the server. */
const FORECASTABLE_ID = /^(\d{7}[NS]\d{5}|SYS_[0-9a-f]{6,32})$/;

/**
 * The trained model's forecast for one cyclone; `null` means "no prediction available" (not an error).
 * GET /api/cyclones/{id}/prediction, or POST /api/ml/predict with VITE_PREDICTION_STRATEGY=inference.
 */
export async function getPrediction(cycloneId: string): Promise<ServiceResult<CyclonePrediction | null>> {
  if (!FORECASTABLE_ID.test(cycloneId)) return live(null);
  const { data: cyclone } = await getCycloneById(cycloneId);
  let response: PredictionResourceResponse | null;
  try {
    response = await fetchLivePrediction(cycloneId);
  } catch (error) {
    if (error instanceof ApiError && NO_FORECAST_STATUSES.includes(error.status)) return live(null);
    throw error;
  }
  // Anchor on the observed state the model actually started from; the registry entry only when the backend omits it.
  const anchor = response?.current ? anchorFromCurrent(response.current) : cyclone ? anchorFrom(cyclone) : null;
  return live(response && anchor ? normalizePrediction(response, anchor, cycloneId) : null);
}

// ── Track forecast from the trained model ────────────────────────────────────

/** GET /api/cyclones/prediction-cases — held-out storms and the times a forecast can start from. */
export async function getPredictionCases(): Promise<ServiceResult<PredictionCasesResponse>> {
  return live(await apiGet<PredictionCasesResponse>("/cyclones/prediction-cases"));
}

/** GET /api/cyclones/{id}/track — observed best-track fixes. */
export async function getObservedTrack(cycloneId: string, range: DateRangeQuery = {}): Promise<ServiceResult<CycloneTrackResponse>> {
  return live(await apiGet<CycloneTrackResponse>(`/cyclones/${enc(cycloneId)}/track`, { start: range.start, end: range.end }));
}

export interface ModelForecast {
  prediction: CyclonePrediction;
  response: PredictionResourceResponse;
}

const PREDICT_TIMEOUT_MS = 30_000;

/**
 * POST /api/ml/predict — run the trained model for one cyclone and forecast time. Returns the raw
 * response and its map/chart-ready CyclonePrediction (normalizePrediction). No ML logic here.
 */
export async function predictCyclone(payload: PredictionRequest): Promise<ServiceResult<ModelForecast>> {
  const response = await apiRequest<PredictionResourceResponse>("/ml/predict", { method: "POST", body: payload, timeoutMs: PREDICT_TIMEOUT_MS });
  if (!response.current || !Array.isArray(response.forecast)) throw new ApiError(200, null, "parse");
  return live({ prediction: normalizePrediction(response, anchorFromCurrent(response.current), response.cycloneId), response });
}

/** "backend_unavailable" = the API cannot be reached at all; the rest are the prediction model's own states. */
export type PredictionServiceState = "backend_unavailable" | PredictionModelState;

export interface PredictionServiceStatus {
  backendReachable: boolean;
  state: PredictionServiceState;
  /** GET /api/ml/status → prediction; null when the backend is unreachable or does not report it. */
  model: PredictionModelStatus | null;
  checkedAt: string;
}

/** GET /api/health (is the backend reachable?) then GET /api/ml/status (is the prediction model loaded?). */
export async function getPredictionServiceStatus(): Promise<ServiceResult<PredictionServiceStatus>> {
  const reachability = await checkApiHealth();
  const { checkedAt } = reachability;
  if (!reachability.reachable) return live({ backendReachable: false, state: "backend_unavailable", model: null, checkedAt });
  try {
    const registry = await apiGet<ModelRegistry>("/ml/status");
    if (registry.prediction) return live({ backendReachable: true, state: registry.prediction.status, model: registry.prediction, checkedAt });
  } catch {
    // Fall back to the health flag below.
  }
  // services.prediction_model is true only when the checkpoint is actually loaded.
  const loaded = reachability.health?.services?.prediction_model === true;
  return live({ backendReachable: true, state: loaded ? "ready" : "unavailable", model: null, checkedAt });
}

/** Positions only — for track overlays. */
export async function getTrackPrediction(cycloneId: string): Promise<ServiceResult<TrackPrediction | null>> {
  const result = await getPrediction(cycloneId);
  const prediction = result.data;
  return {
    source: result.source,
    data: prediction && {
      cycloneId,
      issuedAt: prediction.issuedAt,
      points: prediction.forecast.map(({ id, hours, label, forecastTime, latitude, longitude, confidence, uncertaintyRadiusKm }) => ({ id, hours, label, forecastTime, latitude, longitude, confidence, uncertaintyRadiusKm })),
    },
  };
}

/** Wind/pressure series starting at the observed state — for intensity charts. */
export async function getIntensityPrediction(cycloneId: string): Promise<ServiceResult<IntensityPrediction | null>> {
  const result = await getPrediction(cycloneId);
  const prediction = result.data;
  return {
    source: result.source,
    data: prediction && {
      cycloneId,
      issuedAt: prediction.issuedAt,
      confidence: prediction.confidence.intensity,
      series: [
        { hours: 0, label: "NOW", windKmh: prediction.current.windKmh, pressureHpa: prediction.current.pressureHpa },
        ...prediction.forecast.map((point) => ({ hours: point.hours, label: point.label, windKmh: point.windKmh, pressureHpa: point.pressureHpa })),
      ],
    },
  };
}

/**
 * Detection / classification of a registry cyclone. The backend identifies and classifies uploaded satellite images
 * (identifyImage / classifyImage / analyzeImage below); it has no per-cyclone endpoint and registry cyclones carry no
 * image, so there is nothing to ask — both stay null. Never a mock value, never a request to an endpoint that does not exist.
 */
export async function getMlAssessment(): Promise<ServiceResult<MlAssessment>> {
  return live({ detection: null, classification: null });
}

/** GET /api/ml/status — readiness of the three models (read from the backend's model registry) and their metadata. */
export async function getModelRegistry(): Promise<ServiceResult<ModelRegistry>> {
  return live(await apiGet<ModelRegistry>("/ml/status"));
}

// ── Image upload inference ──────────────────────────────────────────────────
// These always call the backend, in demo mode too: an uploaded image can only be judged by the
// real model, so there is deliberately no mock fallback.
const ML_UPLOAD_TIMEOUT_MS = 60_000;

function imageForm(file: File, metadata?: ImageAnalysisMetadata): FormData {
  const form = new FormData();
  form.append("file", file, file.name);
  for (const [key, value] of Object.entries(metadata ?? {})) {
    if (value) form.append(key, value);
  }
  return form;
}

/**
 * POST /api/ml/analyze — identification, classification only if a cyclone is found, and a track forecast only when
 * `metadata.storm_id` (+ `timestamp`) names a storm whose observation history supports one (`prediction.available`).
 */
export function analyzeImage(file: File, metadata?: ImageAnalysisMetadata): Promise<ImageAnalysisResponse> {
  return apiRequest<ImageAnalysisResponse>("/ml/analyze", { method: "POST", body: imageForm(file, metadata), timeoutMs: ML_UPLOAD_TIMEOUT_MS });
}

/** POST /api/ml/classify — IMD intensity class of an image already known to show a cyclone. */
export function classifyImage(file: File, metadata?: ImageAnalysisMetadata): Promise<ImageClassifyResponse> {
  return apiRequest<ImageClassifyResponse>("/ml/classify", { method: "POST", body: imageForm(file, metadata), timeoutMs: ML_UPLOAD_TIMEOUT_MS });
}

/** POST /api/ml/identify — CYCLONE / NO_CYCLONE only. */
export function identifyImage(file: File, metadata?: ImageAnalysisMetadata): Promise<ImageIdentifyResponse> {
  return apiRequest<ImageIdentifyResponse>("/ml/identify", { method: "POST", body: imageForm(file, metadata), timeoutMs: ML_UPLOAD_TIMEOUT_MS });
}
