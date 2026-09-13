import { THEATRE_VIEW } from "@/lib/mapStyle";
import type { MapBounds, RegionSelection } from "@/types/region";

/**
 * Map camera for every UI region and subregion — the one place region coordinates for the map live.
 * `bounds` is fitted responsively (the map picks the zoom for its size); `center`/`zoom` are the
 * initial camera and the fallback. Keys are UI region ids: geographic views, never IBTrACS basin
 * codes (see types/region.ts). Longitudes east of 180° keep Pacific sectors contiguous.
 */
export interface MapViewport {
  center: [number, number];
  zoom: number;
  bounds?: MapBounds;
}

export const MAP_VIEWPORTS: Record<string, MapViewport> = {
  north_indian_ocean: { center: [72.5, 14], zoom: 3.2, bounds: { north: 30, south: -2, west: 45, east: 100 } },
  arabian_sea: { center: [64, 15.5], zoom: 4, bounds: { north: 26, south: 5, west: 50, east: 78 } },
  bay_of_bengal: { center: [89, 14.5], zoom: 4.2, bounds: { north: 24, south: 5, west: 78, east: 100 } },
  south_indian_ocean: { center: [82.5, -19], zoom: 2.3, bounds: { north: 2, south: -40, west: 30, east: 135 } },
  pacific_ocean: { center: [-167.5, 1.5], zoom: 1.3, bounds: { north: 48, south: -45, west: 100, east: 285 } },
  western_pacific: { center: [140, 22.5], zoom: 2.8, bounds: { north: 45, south: 0, west: 100, east: 180 } },
  eastern_pacific: { center: [-127.5, 17.5], zoom: 2.6, bounds: { north: 35, south: 0, west: 180, east: 285 } },
  southern_pacific: { center: [-175, -22.5], zoom: 2.8, bounds: { north: 0, south: -45, west: 135, east: 235 } },
};

/** The North Indian Ocean theatre, used before any region is known. */
export const DEFAULT_VIEWPORT: MapViewport = { center: THEATRE_VIEW.center, zoom: THEATRE_VIEW.zoom };

const normalizeLon = (longitude: number) => ((((longitude + 180) % 360) + 360) % 360) - 180;

/** Camera for a selection; regions added later through GET /api/regions fall back to their `mapBounds`. */
export function viewportFor(selection: RegionSelection, fallbackBounds?: MapBounds): MapViewport {
  const configured = (selection.subregionId && MAP_VIEWPORTS[selection.subregionId]) || MAP_VIEWPORTS[selection.regionId];
  if (configured) return configured;
  if (!fallbackBounds) return DEFAULT_VIEWPORT;
  const center: [number, number] = [normalizeLon((fallbackBounds.west + fallbackBounds.east) / 2), (fallbackBounds.north + fallbackBounds.south) / 2];
  return { center, zoom: 2, bounds: fallbackBounds };
}
