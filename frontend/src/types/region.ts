import type { CycloneCategory, CycloneStatus, RiskLevel } from "./cyclone";
import type { SatelliteChannelId } from "./satellite";

/*
 * Two taxonomies live side by side and must never be merged:
 *
 *   UI hierarchy (what operators navigate)      Dataset taxonomy (what the data layer stores)
 *   north_indian_ocean → arabian_sea            IBTrACS BASIN = NI
 *   north_indian_ocean → bay_of_bengal          IBTrACS BASIN = NI
 *   south_indian_ocean                          IBTrACS BASIN = SI
 *   pacific_ocean → western_pacific             IBTrACS BASIN = WP
 *   pacific_ocean → eastern_pacific             IBTrACS BASIN = EP
 *   pacific_ocean → southern_pacific            IBTrACS BASIN = SP
 *
 * A region/subregion id is a geographic view, never a basin code. "Arabian Sea" is not an
 * IBTrACS basin — it is a focused sub-view of the NI basin.
 */

/** IBTrACS basin codes — the meteorological data-layer taxonomy. */
export type IbtracsBasin = "NA" | "SA" | "EP" | "WP" | "SP" | "SI" | "NI";

export type RegionId = string;
export type SubregionId = string;

/** Geographic viewport in degrees. `east` may exceed 180 for sectors that cross the antimeridian. */
export interface MapBounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

/** Named place used for map tags and mock-imagery annotation. Longitudes are standard [-180, 180]. */
export interface RegionLandmark {
  label: string;
  latitude: number;
  longitude: number;
}

/** `primary` = the project's home theatre, `overview` = a wide multi-basin summary view. */
export type RegionEmphasis = "primary" | "standard" | "overview";

export interface Subregion {
  id: SubregionId;
  name: string;
  shortName: string;
  parentRegion: RegionId;
  description?: string;
  /** Dataset basins this view draws from. Siblings may share one (Arabian Sea and Bay of Bengal are both NI). */
  basins: IbtracsBasin[];
  /** Regional Specialised Meteorological Centre(s) responsible for warnings in this sector. */
  rsmc?: string;
  season?: string;
  mapBounds?: MapBounds;
  landmarks?: RegionLandmark[];
}

export interface Region {
  id: RegionId;
  name: string;
  shortName: string;
  description?: string;
  emphasis: RegionEmphasis;
  basins: IbtracsBasin[];
  rsmc?: string;
  season?: string;
  subregions?: Subregion[];
  mapBounds?: MapBounds;
  landmarks?: RegionLandmark[];
}

/** The operator's current geographic focus. `subregionId` undefined = region-wide / overview. */
export interface RegionSelection {
  regionId: RegionId;
  subregionId?: SubregionId;
}

/** Active-system roll-up for one region or subregion. */
export interface RegionSummary {
  regionId: RegionId;
  subregionId?: SubregionId;
  activeSystems: number;
  strongestCycloneId?: string;
  strongestCode?: string;
  maxWindKmh?: number;
}

// ── Satellite sources and their regional availability ─────────────────────

export type SatelliteSourceId = string;

/** How well a geostationary source sees a sector: near nadir, oblique, or at the disk limb. */
export type SatelliteCoverageTier = "primary" | "secondary" | "limb";

export interface SatelliteBand {
  band: string;
  wavelengthUm: number;
  resolutionKm: number;
}

export interface SatelliteSource {
  id: SatelliteSourceId;
  name: string;
  family: string;
  agency: string;
  dataProvider?: string;
  instrument: string;
  /** Operational slot name, e.g. "GOES-West" or "IODC". */
  serviceSlot?: string;
  subSatelliteLongitude: number;
  cadenceMinutes: number;
  channels: Partial<Record<SatelliteChannelId, SatelliteBand>>;
}

export interface SatelliteSourceCoverage {
  sourceId: SatelliteSourceId;
  tier: SatelliteCoverageTier;
  note?: string;
}

/** Which sources can observe a region/subregion. Phase 4: part of GET /api/satellite?region=… */
export interface SatelliteAvailability {
  regionId: RegionId;
  subregionId?: SubregionId;
  defaultSourceId: SatelliteSourceId;
  sources: SatelliteSourceCoverage[];
}

// ── Regional cyclone observation (per timeline slot) ──────────────────────

export interface ObservedSystem {
  cycloneId: string;
  code: string;
  name: string;
  category: CycloneCategory;
  status: CycloneStatus;
  riskLevel: RiskLevel;
  basin: IbtracsBasin;
  regionId: RegionId;
  subregionId?: SubregionId;
  latitude: number;
  longitude: number;
  windKmh: number;
  pressureHpa: number;
  confidence: number;
}

/** Systems inside a region at one observation time. Phase 4: GET /api/cyclones?region=…&at=… */
export interface RegionalCycloneObservation {
  regionId: RegionId;
  subregionId?: SubregionId;
  timestamp: string;
  activeSystems: number;
  /** Sorted strongest first. */
  systems: ObservedSystem[];
  strongest?: ObservedSystem;
}
