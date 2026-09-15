// Region taxonomy + coastal gazetteer, served by the backend (reference geography). UI region ids are geographic
// views; the IBTrACS basins each region draws from are part of the payload (never used as ids).
import { apiGet, orNullOn404 } from "./apiClient";
import { serve } from "./dataMode";
import type { ServiceResult } from "@/types/api";
import type { Region } from "@/types/region";
import type { CoastalDistrict } from "@/types/track";

/** GET /api/regions */
export function getRegions(): Promise<ServiceResult<Region[]>> {
  return serve({ live: () => apiGet<Region[]>("/regions") });
}

/** GET /api/regions/{regionId} */
export function getRegion(regionId: string): Promise<ServiceResult<Region | null>> {
  return serve({ live: () => orNullOn404(apiGet<Region>(`/regions/${encodeURIComponent(regionId)}`)) });
}

/** GET /api/regions/coastal-districts — approximate centroids used for the risk-zone impact popup. */
export function getCoastalDistricts(): Promise<ServiceResult<CoastalDistrict[]>> {
  return serve({ live: () => apiGet<CoastalDistrict[]>("/regions/coastal-districts") });
}
