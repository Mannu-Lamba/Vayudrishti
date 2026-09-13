import { selectionKey } from "@/lib/regions";
import { getArchiveSummary, getCycloneArchive, getCyclones, getRecentEvents, getRegionalObservation } from "@/services/cycloneApi";
import { useServiceQuery } from "./useServiceQuery";
import type { CycloneArchiveQuery, CycloneQuery } from "@/types/cyclone";
import type { RegionSelection } from "@/types/region";

export type CycloneFilters = Omit<CycloneQuery, "region" | "subregion">;

/** All systems, or those in a region/subregion, optionally narrowed by basin / date / active (GET /api/cyclones?…). */
export function useCyclones(selection?: RegionSelection, filters: CycloneFilters = {}) {
  return useServiceQuery(
    ["cyclones", selection ? selectionKey(selection) : "all", filters],
    () => getCyclones({ region: selection?.regionId, subregion: selection?.subregionId, ...filters }),
  );
}

/** Systems in a sector at one observation time. */
export function useRegionalObservation(selection: RegionSelection, at: string | undefined) {
  return useServiceQuery(["regional-observation", selectionKey(selection), at], () => getRegionalObservation(selection, at ?? ""), { enabled: Boolean(at), keepPrevious: true });
}

export function useArchiveSummary() {
  return useServiceQuery(["archive-summary"], getArchiveSummary);
}

export function useRecentEvents(limit = 10) {
  return useServiceQuery(["recent-events", limit], () => getRecentEvents(limit));
}

/** Paged historical archive. */
export function useCycloneArchive(query: CycloneArchiveQuery = {}) {
  return useServiceQuery(["cyclone-archive", query], () => getCycloneArchive(query), { keepPrevious: true });
}
