import { viewportFor, type MapViewport } from "@/config/mapViewports";
import { inBounds } from "@/lib/geo";
import type { CycloneData } from "@/types/cyclone";
import type { IbtracsBasin, MapBounds, Region, RegionLandmark, RegionSelection, RegionSummary, Subregion } from "@/types/region";

// Pure helpers over the region configuration. They take `regions` as input so the same code
// works whether the config comes from mock data (Phase 3) or GET /api/regions (Phase 4).

const WORLD_BOUNDS: MapBounds = { north: 60, south: -60, west: -180, east: 180 };

export function findRegion(regions: Region[], regionId: string | null | undefined): Region | undefined {
  return regions.find((region) => region.id === regionId);
}

export function findSubregion(region: Region | undefined, subregionId: string | null | undefined): Subregion | undefined {
  return region?.subregions?.find((subregion) => subregion.id === subregionId);
}

export function defaultRegion(regions: Region[]): Region | undefined {
  return regions.find((region) => region.emphasis === "primary") ?? regions[0];
}

/** Validate raw URL params against the config; unknown ids fall back to the primary region-wide view. */
export function resolveSelection(regions: Region[], regionParam: string | null, subregionParam: string | null): RegionSelection {
  const region = findRegion(regions, regionParam) ?? defaultRegion(regions);
  if (!region) return { regionId: regionParam ?? "" };
  const subregion = findSubregion(region, subregionParam);
  return subregion ? { regionId: region.id, subregionId: subregion.id } : { regionId: region.id };
}

export function selectionKey(selection: RegionSelection) {
  return `${selection.regionId}/${selection.subregionId ?? "*"}`;
}

export interface SelectionDetails {
  region?: Region;
  subregion?: Subregion;
  /** "North Indian Ocean" or "Arabian Sea". */
  label: string;
  /** "North Indian Ocean › Arabian Sea". */
  path: string;
  /** Geographic extent of the view (sector outlines, imagery frames). */
  bounds: MapBounds;
  /** Map camera for the view (config/mapViewports.ts). */
  viewport: MapViewport;
  landmarks: RegionLandmark[];
  basins: IbtracsBasin[];
  rsmc?: string;
  season?: string;
  description?: string;
}

export function describeSelection(regions: Region[], selection: RegionSelection): SelectionDetails {
  const region = findRegion(regions, selection.regionId);
  const subregion = findSubregion(region, selection.subregionId);
  const view = subregion ?? region;
  const bounds = subregion?.mapBounds ?? region?.mapBounds ?? WORLD_BOUNDS;
  return {
    region,
    subregion,
    label: view?.name ?? "Region data unavailable",
    path: subregion && region ? `${region.name} › ${subregion.name}` : region?.name ?? "Region data unavailable",
    bounds,
    // The camera config is keyed by region id, so it works even when the region list failed to load.
    viewport: viewportFor(selection, view ? bounds : undefined),
    landmarks: view?.landmarks ?? [],
    basins: view?.basins ?? [],
    rsmc: view?.rsmc,
    season: view?.season,
    description: view?.description,
  };
}

/**
 * Map a dataset record (IBTrACS basin + position) onto the UI hierarchy. The basin picks the
 * region; when several subregions share that basin (NI → Arabian Sea / Bay of Bengal) the
 * position decides. This is the only bridge between the two taxonomies.
 */
export function resolveCycloneArea(regions: Region[], cyclone: Pick<CycloneData, "basin" | "location">): RegionSelection | null {
  const region = regions.find((candidate) => candidate.basins.includes(cyclone.basin));
  if (!region) return null;
  const { latitude, longitude } = cyclone.location;
  const candidates = (region.subregions ?? []).filter((subregion) => subregion.basins.includes(cyclone.basin));
  const subregion = candidates.length === 1
    ? candidates[0]
    : candidates.find((candidate) => candidate.mapBounds && inBounds(candidate.mapBounds, latitude, longitude));
  return subregion ? { regionId: region.id, subregionId: subregion.id } : { regionId: region.id };
}

export function cycloneInSelection(regions: Region[], cyclone: Pick<CycloneData, "basin" | "location">, selection: RegionSelection) {
  const area = resolveCycloneArea(regions, cyclone);
  if (!area || area.regionId !== selection.regionId) return false;
  return !selection.subregionId || area.subregionId === selection.subregionId;
}

export type RegionSummaryIndex = Map<string, RegionSummary>;

/** Active-system counts and strongest system for every region and subregion. */
export function summarizeRegions(regions: Region[], cyclones: CycloneData[]): RegionSummaryIndex {
  const index: RegionSummaryIndex = new Map();
  const bump = (selection: RegionSelection, cyclone: CycloneData) => {
    const key = selectionKey(selection);
    const current = index.get(key) ?? { ...selection, activeSystems: 0 };
    current.activeSystems += 1;
    if (cyclone.windKmh > (current.maxWindKmh ?? -1)) {
      current.maxWindKmh = cyclone.windKmh;
      current.strongestCycloneId = cyclone.id;
      current.strongestCode = cyclone.code;
    }
    index.set(key, current);
  };
  for (const cyclone of cyclones) {
    const area = resolveCycloneArea(regions, cyclone);
    if (!area) continue;
    bump({ regionId: area.regionId }, cyclone);
    if (area.subregionId) bump(area, cyclone);
  }
  return index;
}

export function summaryFor(index: RegionSummaryIndex, selection: RegionSelection): RegionSummary {
  return index.get(selectionKey(selection)) ?? { ...selection, activeSystems: 0 };
}

/** Subregion outlines for the map, with the selected one highlighted. */
export function sectorsFor(region: Region | undefined, activeSubregionId?: string) {
  return (region?.subregions ?? []).flatMap((subregion) => (subregion.mapBounds
    ? [{ id: subregion.id, label: subregion.name, bounds: subregion.mapBounds, active: subregion.id === activeSubregionId }]
    : []));
}

export function padCount(value: number) {
  return String(value).padStart(2, "0");
}
