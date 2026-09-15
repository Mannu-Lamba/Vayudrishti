import type { MapBounds, RegionId, SatelliteAvailability, SatelliteCoverageTier, SatelliteSource, SatelliteSourceId, SubregionId } from "./region";

/** Phase 1 display label, still used by the dashboard's latest-frame card. */
export type SatelliteChannel = "Infrared" | "Water Vapor" | "Visible";

export interface SatelliteFrame {
  id: string;
  source: string;
  satellite: string;
  channel: SatelliteChannel | null;
  capturedAt: string;
  /** unavailable = the database stores no image for this frame. */
  status: "processed" | "queued" | "unavailable";
  region: string;
  resolutionKm: number | null;
  cloudTopTemperature: string | null;
  enhancement: string | null;
  /** classification_results label of the frame, e.g. "cyclone (class 1)". */
  datasetLabel?: string | null;
}

// ── Phase 3: multi-region, multi-source observations ──────────────────────

/** Stable channel ids shared with the future /api/satellite contract. */
export type SatelliteChannelId = "visible" | "infrared" | "water_vapor";

export interface SatelliteChannelSpec {
  id: SatelliteChannelId;
  label: string;
  shortLabel: string;
  description: string;
  /** Visible imagery needs solar illumination; frames at local night are unavailable. */
  requiresDaylight: boolean;
}

export type SatelliteProcessingStatus = "processed" | "processing" | "missing";

/** not_stored = the frame is recorded in the database but no image file is stored for it. */
export type SatelliteUnavailableReason = "local_night" | "scan_gap" | "processing" | "no_coverage" | "not_stored";

/** A cyclone located in a frame. Phase 4: produced by POST /api/ml/detect. */
export interface SatelliteDetection {
  cycloneId: string;
  code: string;
  latitude: number;
  longitude: number;
  confidence: number;
}

/** One frame from one source, channel and sector. Optional fields may be absent in real feeds. */
export interface SatelliteObservation {
  id: string;
  regionId: RegionId;
  subregionId?: SubregionId;
  source: SatelliteSourceId;
  /** null when the database did not record the channel. */
  channel: SatelliteChannelId | null;
  /** Actual scan time (ISO 8601, UTC). */
  timestamp: string;
  /** Nominal timeline slot this frame is filed under. */
  slotId: string;
  imageUrl?: string | null;
  /** Geographic extent of `imageUrl`, used to place detections over the image. */
  bounds?: MapBounds | null;
  cycloneId?: string | null;
  /** classification_results label of the frame, e.g. "no cyclone (class 0)". */
  datasetLabel?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  coverage?: string;
  coverageTier?: SatelliteCoverageTier;
  resolution?: string;
  processingStatus?: SatelliteProcessingStatus;
  processingLevel?: string;
  /** Local solar time at the sector centre, "HH:MM". */
  localSolarTime?: string;
  available: boolean;
  unavailableReason?: SatelliteUnavailableReason;
  detections?: SatelliteDetection[];
}

export interface SatelliteTimeSlot {
  id: string;
  label: string;
  timestamp: string;
}

/** GET /api/satellite/sources?region=…&subregion=… */
export interface SatelliteSourceCatalog {
  availability: SatelliteAvailability | null;
  sources: SatelliteSource[];
}

/** GET /api/satellite?region=…&subregion=…&source=…&channel=…&start=…&end=…&page=…&pageSize=… */
export interface SatelliteObservationQuery {
  regionId: RegionId;
  subregionId?: SubregionId;
  source?: SatelliteSourceId;
  channel?: SatelliteChannelId;
  start?: string;
  end?: string;
  page?: number;
  pageSize?: number;
}

/** Composite the satellite workspace renders for one sector (sources + observations + channels). */
export interface SatelliteCatalog {
  regionId: RegionId;
  subregionId?: SubregionId;
  availability: SatelliteAvailability | null;
  sources: SatelliteSource[];
  channels: SatelliteChannelSpec[];
  slots: SatelliteTimeSlot[];
  /** Frame metadata only — images are fetched per frame. */
  observations: SatelliteObservation[];
}
