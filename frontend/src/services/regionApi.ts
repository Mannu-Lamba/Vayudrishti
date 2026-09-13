// Region taxonomy + coastal gazetteer. UI region ids are geographic views; the IBTrACS basins
// each region draws from are part of the payload (never used as ids).
import { coastalDistricts } from "@/data/mock/coastalDistricts";
import { mockRegions } from "@/data/mock/regions";
import { apiGet, orNullOn404 } from "./apiClient";
import { serve } from "./dataMode";
import type { ServiceResult } from "@/types/api";
import type { Region } from "@/types/region";
import type { CoastalDistrict } from "@/types/track";

/** GET /api/regions */
export function getRegions(): Promise<ServiceResult<Region[]>> {
  return serve({ demo: () => mockRegions, live: () => apiGet<Region[]>("/regions") });
}

/** GET /api/regions/{regionId} */
export function getRegion(regionId: string): Promise<ServiceResult<Region | null>> {
  return serve({
    demo: () => mockRegions.find((region) => region.id === regionId) ?? null,
    live: () => orNullOn404(apiGet<Region>(`/regions/${encodeURIComponent(regionId)}`)),
  });
}

/** GET /api/regions/coastal-districts — centroids used for the risk-zone impact popup. */
export function getCoastalDistricts(): Promise<ServiceResult<CoastalDistrict[]>> {
  return serve({ demo: () => coastalDistricts, live: () => apiGet<CoastalDistrict[]>("/regions/coastal-districts") });
}
