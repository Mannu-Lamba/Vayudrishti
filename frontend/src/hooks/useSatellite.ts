import { useQueries } from "@tanstack/react-query";
import { selectionKey } from "@/lib/regions";
import { getLatestSatelliteFrame, getSatelliteCatalog, getSatelliteObservationById } from "@/services/satelliteApi";
import { useDataMode } from "./useDataMode";
import { DATA_QUERY_ROOT, dataQueryOptions, useServiceQuery } from "./useServiceQuery";
import type { RegionSelection } from "@/types/region";

export function useSatelliteCatalog(selection: RegionSelection) {
  return useServiceQuery(["satellite-catalog", selectionKey(selection)], () => getSatelliteCatalog(selection));
}

/** One frame with its image. `keepPrevious` keeps the last image on screen while the next loads. */
export function useSatelliteObservation(id: string | undefined, options: { keepPrevious?: boolean } = {}) {
  return useServiceQuery(["satellite-observation", id], () => getSatelliteObservationById(id ?? ""), { enabled: Boolean(id), keepPrevious: options.keepPrevious });
}

/** Several frames at once (multi-source comparison); shares the cache with useSatelliteObservation. */
export function useSatelliteObservations(ids: (string | undefined)[]) {
  const { mode } = useDataMode();
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: [DATA_QUERY_ROOT, mode, "satellite-observation", id],
      queryFn: () => getSatelliteObservationById(id ?? ""),
      enabled: Boolean(id),
      ...dataQueryOptions(mode),
    })),
  });
  return results.map((result) => ({ data: result.data?.data, source: result.data?.source, loading: result.isLoading, fetching: result.isFetching, error: result.error }));
}

export function useLatestSatelliteFrame(regionId?: string) {
  return useServiceQuery(["satellite-latest", regionId], () => getLatestSatelliteFrame(regionId));
}
