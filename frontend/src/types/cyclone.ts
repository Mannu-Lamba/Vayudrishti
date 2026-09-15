import type { IbtracsBasin } from "./region";

/** historical = last observed more than 24 h ago (every storm in the database today). */
export type CycloneStatus = "active" | "monitoring" | "dissipating" | "historical";
export type CycloneCategory =
  // IMD scale (RSMC New Delhi) — the scale the backend applies in every basin
  | "Low Pressure Area"
  | "Depression"
  | "Deep Depression"
  | "Cyclonic Storm"
  | "Severe Cyclonic Storm"
  | "Very Severe Cyclonic Storm"
  | "Extremely Severe Cyclonic Storm"
  | "Super Cyclonic Storm"
  // Other RSMC scales used by the multi-region registry
  | "Tropical Depression"
  | "Moderate Tropical Storm"
  | "Tropical Storm"
  | "Severe Tropical Storm"
  | "Typhoon"
  | "Hurricane";
export type RiskLevel = "low" | "moderate" | "high" | "severe";

export interface CycloneLocation {
  latitude: number;
  longitude: number;
  label: string;
}

/**
 * One storm of the registry (GET /api/cyclones, GET /api/cyclones/{id}) — a real storm from cyclone_database.
 * Tracks are not embedded: they are requested from GET /api/cyclones/{id}/track when a system is selected.
 * A value the data does not hold is null and shown as "—", never filled in.
 */
export interface CycloneData {
  id: string;
  code: string;
  name: string;
  status: CycloneStatus;
  /** IMD category of the wind at `observedAt`, assigned by the backend; null when no wind was observed. */
  category: CycloneCategory | null;
  /** Area label, e.g. "Bay of Bengal". The UI region/subregion is derived from `basin` + position (lib/regions.ts). */
  region: string;
  /** IBTrACS basin — data-layer taxonomy. */
  basin: IbtracsBasin;
  windKmh: number | null;
  pressureHpa: number | null;
  movementDirection: string | null;
  movementSpeedKmh: number | null;
  /** Not in the database: always null today. */
  detectionConfidence: number | null;
  dvorakTNumber: string | null;
  /** No risk model is deployed: always null today. */
  riskLevel: RiskLevel | null;
  location: CycloneLocation;
  /** Time of the latest observation, ISO 8601 UTC. */
  observedAt: string;
  firstObservedAt?: string;
  season?: number;
  fixes?: number;
  peakWindKmh?: number | null;
  peakCategory?: string | null;
  /** cyclone_database and/or the held-out IBTrACS best track. */
  source?: string;
  /** At least one fix has a full 24 h history with observed wind + pressure, so the prediction model can forecast this storm. */
  forecastAvailable?: boolean;
  /** Latest fix a forecast can start from (the default forecast time of GET /cyclones/{id}/prediction); null when none. */
  forecastOrigin?: string | null;
}

/**
 * Filters for GET /api/cyclones. Region ids are UI views; the backend maps IBTrACS basin + position
 * onto them, so there is no "Arabian Sea" basin — `basin` filters on the dataset code itself.
 */
export interface CycloneQuery {
  region?: string;
  subregion?: string;
  /** IBTrACS basin code, e.g. "NI". */
  basin?: IbtracsBasin;
  /** ISO 8601 bounds on the latest observation time. */
  startDate?: string;
  endDate?: string;
  /** true = currently tracked systems (the operational registry); false = systems no longer tracked. */
  active?: boolean;
}

/** GET /api/cyclones/archive — paged, filterable; the browser never loads the whole archive. */
export interface CycloneArchiveQuery {
  region?: string;
  subregion?: string;
  year?: number;
  page?: number;
  pageSize?: number;
}

export interface HistoricalCyclone {
  id: string;
  name: string;
  year: number;
  /** IBTrACS basin code (data layer). */
  basin: IbtracsBasin;
  /** Geographic area within the basin (UI label), e.g. "Arabian Sea". */
  area: string;
  /** IMD category of the peak observed wind. */
  category: CycloneCategory | string | null;
  peakWindKmh: number | null;
  /** Not in the database: null. */
  landfall: string | null;
  casualties: number | null;
  firstObservedAt?: string;
  lastObservedAt?: string;
  source?: string;
}

/** GET /api/cyclones/archive/summary — aggregated server-side, never computed from the raw dataset here. */
export interface ArchiveSummary {
  indexedSystems: number;
  firstYear: number;
  lastYear: number;
  coverage: string;
  seasons: { season: string; storms: number }[];
}

/** GET /api/events — today: "record" = the latest observation of a storm in the database. */
export interface OperationalEvent {
  id: string;
  kind: "alert" | "satellite" | "forecast" | "record";
  priority: "high" | "info";
  title: string;
  source: string;
  /** ISO 8601, UTC. */
  timestamp: string;
  cycloneId?: string;
}
