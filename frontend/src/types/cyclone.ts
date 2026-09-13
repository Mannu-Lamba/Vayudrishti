import type { IbtracsBasin } from "./region";

export type CycloneStatus = "active" | "monitoring" | "dissipating";
export type CycloneCategory =
  // IMD scale (RSMC New Delhi) — North Indian Ocean
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
 * One system in the operational registry (GET /api/cyclones, GET /api/cyclones/{id}).
 * Tracks are not embedded: they are requested from GET /api/cyclones/{id}/track when a system is selected.
 */
export interface CycloneData {
  id: string;
  code: string;
  name: string;
  status: CycloneStatus;
  /** As assigned by the backend / warning centre. The frontend never derives it from wind speed. */
  category: CycloneCategory;
  /** Display label only. The UI region/subregion is derived from `basin` + position (lib/regions.ts). */
  region: "Arabian Sea" | "Bay of Bengal" | "Indian Ocean" | "South Indian Ocean" | "Western Pacific" | "Eastern Pacific" | "Southern Pacific";
  /** IBTrACS basin — data-layer taxonomy, as the backend will return it. */
  basin: IbtracsBasin;
  windKmh: number;
  pressureHpa: number;
  movementDirection: string;
  movementSpeedKmh: number;
  detectionConfidence: number;
  dvorakTNumber: string;
  riskLevel: RiskLevel;
  location: CycloneLocation;
  /** Time of the latest observation. */
  observedAt: string;
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
  category: CycloneCategory;
  peakWindKmh: number;
  landfall: string;
  casualties: number;
}

/** GET /api/cyclones/archive/summary — aggregated server-side, never computed from the raw dataset here. */
export interface ArchiveSummary {
  indexedSystems: number;
  firstYear: number;
  lastYear: number;
  coverage: string;
  seasons: { season: string; storms: number }[];
}

/** GET /api/events — operational feed (alerts, processed frames, forecast runs). */
export interface OperationalEvent {
  id: string;
  kind: "alert" | "satellite" | "forecast";
  priority: "high" | "info";
  title: string;
  source: string;
  /** ISO 8601, UTC. */
  timestamp: string;
  cycloneId?: string;
}
