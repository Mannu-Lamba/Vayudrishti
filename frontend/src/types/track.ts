import type { CycloneCategory, CycloneStatus } from "./cyclone";

/**
 * One track fix as FastAPI returns it (GET /api/cyclones/{id}/track). Units are explicit in the
 * field names. Display labels and lead times are derived in the frontend (cycloneApi.normalizeTrack),
 * so the backend only sends measured values.
 */
export interface TrackPoint {
  /** ISO 8601, UTC. */
  timestamp: string;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  /** Category the backend assigned at this fix. Never inferred from wind speed in the frontend. */
  category?: CycloneCategory | string;
  /** true for forecast fixes; observed (best-track) fixes omit it. */
  forecast?: boolean;
  /** 0–1 or 0–100. */
  confidence?: number;
  /** Forecast fixes only: radius of the uncertainty circle. */
  uncertaintyRadiusKm?: number;
}

/** GET /api/cyclones/{id}/track?start=…&end=… */
export interface CycloneTrackResponse {
  cycloneId: string;
  /** Time of the latest observation; lead times are measured from it. Defaults to the last observed fix. */
  observedAt?: string;
  points: TrackPoint[];
  uncertaintyKm?: { start: number; end: number };
  riskZones?: RiskZoneSpec[];
}

export type RiskZoneLevel = "low" | "moderate" | "high" | "severe";

/** A geo-referenced storm fix as the map draws it. `offsetHours` is relative to the latest observation (negative = past). */
export interface GeoTrackPoint {
  id: string;
  /** "NOW", "T-18h", "T+6h". */
  label: string;
  offsetHours: number;
  /** Display time, e.g. "08 Sep · 14:30 UTC". */
  timestamp: string;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  /** Percent, when the source provides one. */
  confidence?: number;
  category?: CycloneCategory | string;
  forecast: boolean;
  /** Forecast fixes only: radius of the uncertainty circle around the fix. */
  uncertaintyRadiusKm?: number;
}

/** One system drawn on the map, built by the page from API data (lib/mapScene.ts#toMapMarkers). */
export interface MapCycloneMarker {
  id: string;
  code: string;
  name: string;
  category: CycloneCategory | string;
  status: CycloneStatus;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  /** Display time of the position. */
  observedAt?: string;
}

/** Request state of the data behind the map. The map stays visible and interactive either way. */
export interface MapDataStatus {
  loading?: boolean;
  /** e.g. "LOADING CYCLONE DATA". */
  loadingLabel?: string;
  error?: unknown;
  onRetry?: () => void;
}

/**
 * Everything the map draws for the selected cyclone. Built from a track (GET /api/cyclones/{id}/track)
 * and, when one exists, a prediction (lib/mapScene.ts). The map never fetches or invents data itself.
 */
export interface CycloneMapScene {
  cycloneId: string;
  currentPosition: GeoTrackPoint;
  /** Past fixes ending with the current position. */
  historicalTrack: GeoTrackPoint[];
  /** Predicted fixes (prediction service only); each may carry `uncertaintyRadiusKm`. */
  forecastPoints: GeoTrackPoint[];
  /** Fallback corridor half-width when forecast points carry no radius. */
  uncertaintyKm: { start: number; end: number };
  /** Backend-supplied prediction polygon ([lon, lat] ring); takes precedence over radii. */
  uncertaintyPolygon?: [number, number][];
  riskZones: RiskZoneSpec[];
}

/** Normalised track for one cyclone — the output of cycloneApi.normalizeTrack. */
export interface CycloneGeoTrack {
  cycloneId: string;
  history: GeoTrackPoint[];
  forecast: GeoTrackPoint[];
  /** Corridor half-width in km at the first and last forecast fix. */
  uncertaintyKm: { start: number; end: number };
  riskZones: RiskZoneSpec[];
}

/** Circular stand-in for a model-generated risk polygon. */
export interface RiskZoneSpec {
  id: string;
  level: RiskZoneLevel;
  radiusKm: number;
  center: { latitude: number; longitude: number };
  label: string;
}

/** Coastal administrative district used for impact assessment (GET /api/regions/coastal-districts). */
export interface CoastalDistrict {
  id: string;
  name: string;
  state: string;
  latitude: number;
  longitude: number;
}

/** A district found to fall inside a clicked risk zone, with its distance from the zone center. */
export interface CoastalImpact {
  district: CoastalDistrict;
  distanceKm: number;
}
