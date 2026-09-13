import type { CycloneCategory } from "./cyclone";

/**
 * Normalised prediction model used by every UI component. Services adapt whatever the backend
 * returns (GET /api/cyclones/{id}/prediction or POST /api/ml/predict) into this shape.
 */

/** Lead time in hours. Today 6 / 12 / 18 / 24; 36 / 48 / 72 need no component changes. */
export type ForecastHours = number;

export interface ForecastPoint {
  id: string;
  hours: ForecastHours;
  /** "T+12h" */
  label: string;
  /** ISO 8601, UTC. */
  forecastTime: string;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  /** 0–1, only when the model produces one. The live track model does not — never shown as 0 %. */
  confidence?: number;
  /** Radius of the uncertainty circle around this fix, when provided. */
  uncertaintyRadiusKm?: number;
  /** Empirical [low, high] wind band (km/h), when provided. */
  windRangeKmh?: [number, number];
  /** IMD category of the predicted wind, when provided. */
  category?: string;
}

/** The observed state a forecast starts from. */
export interface PredictionAnchor {
  observedAt: string;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  category: CycloneCategory | string;
  movementDirection?: string;
  movementSpeedKmh?: number;
}

/**
 * 0–1 scores. Track/intensity arrive with the forecast; classification/detection may instead
 * come from POST /api/ml/classify and POST /api/ml/detect.
 */
export interface PredictionConfidence {
  track?: number;
  intensity?: number;
  classification?: number;
  detection?: number;
}

export interface PredictionUncertainty {
  /**
   * "demo" = illustrative radii only, never presented as model-derived; "model" = from the model;
   * "empirical" = radius holding `confidenceLevel` of the model's validation errors (not per-forecast).
   */
  method: "demo" | "model" | "empirical";
  /** Backend prediction polygon / probability cone ring as [lon, lat] pairs. */
  polygon?: [number, number][];
  /** Probability the cone represents, e.g. 0.67. */
  confidenceLevel?: number;
  note?: string;
}

export interface CyclonePrediction {
  cycloneId: string;
  issuedAt: string;
  modelVersion?: string;
  current: PredictionAnchor;
  /** Sorted by lead time. */
  forecast: ForecastPoint[];
  confidence: PredictionConfidence;
  uncertainty?: PredictionUncertainty;
  /** When the backend computed the forecast (issuedAt is the forecast time T0). */
  generatedAt?: string;
  disclaimer?: string;
}

export interface TrackPrediction {
  cycloneId: string;
  issuedAt: string;
  points: Pick<ForecastPoint, "id" | "hours" | "label" | "forecastTime" | "latitude" | "longitude" | "confidence" | "uncertaintyRadiusKm">[];
}

export interface IntensityPrediction {
  cycloneId: string;
  issuedAt: string;
  confidence?: number;
  series: { hours: ForecastHours; label: string; windKmh: number; pressureHpa: number }[];
}
