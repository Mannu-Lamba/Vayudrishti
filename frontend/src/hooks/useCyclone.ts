import { getCycloneById, getCycloneHistory, getCycloneTrack } from "@/services/cycloneApi";
import { useServiceQuery } from "./useServiceQuery";
import type { DateRangeQuery, PageQuery } from "@/types/api";

export function useCyclone(id: string | undefined) {
  return useServiceQuery(["cyclone", id], () => getCycloneById(id ?? ""), { enabled: Boolean(id) });
}

/** Observed + forecast fixes for the map. `range` bounds long tracks (start/end ISO). */
export function useCycloneTrack(id: string | undefined, range: DateRangeQuery = {}) {
  return useServiceQuery(["cyclone-track", id, range.start, range.end], () => getCycloneTrack(id ?? "", range), { enabled: Boolean(id) });
}

export function useCycloneHistory(id: string | undefined, query: PageQuery & DateRangeQuery = {}) {
  return useServiceQuery(["cyclone-history", id, query], () => getCycloneHistory(id ?? "", query), { enabled: Boolean(id), keepPrevious: true });
}
