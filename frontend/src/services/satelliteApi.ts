// Satellite sources and frame records from MongoDB cyclone_database. A frame's image arrives via `imageUrl`;
// when the database stores no image the frame is reported unavailable ("not_stored") — nothing is rendered in its place.
import { SATELLITE_CHANNELS } from "@/config/satelliteChannels";
import { apiGet, orNullOn404 } from "./apiClient";
import { serve } from "./dataMode";
import type { Paginated, ServiceResult } from "@/types/api";
import type { RegionSelection } from "@/types/region";
import type { SatelliteCatalog, SatelliteFrame, SatelliteObservation, SatelliteObservationQuery, SatelliteSourceCatalog, SatelliteTimeSlot } from "@/types/satellite";

/** GET /api/satellite/sources?region=…&subregion=… — which sources have frame records in the sector. */
export function getSatelliteSources(selection: RegionSelection): Promise<ServiceResult<SatelliteSourceCatalog>> {
  return serve({ live: () => apiGet<SatelliteSourceCatalog>("/satellite/sources", { region: selection.regionId, subregion: selection.subregionId }) });
}

/** GET /api/satellite?region=…&source=…&channel=…&start=…&end=…&page=… — frame metadata only, paged. */
export function getSatelliteObservations(query: SatelliteObservationQuery): Promise<ServiceResult<Paginated<SatelliteObservation>>> {
  return serve({
    live: () => apiGet<Paginated<SatelliteObservation>>("/satellite", {
      region: query.regionId, subregion: query.subregionId, source: query.source, channel: query.channel,
      start: query.start, end: query.end, page: query.page, pageSize: query.pageSize,
    }),
  });
}

/** GET /api/satellite/{id} — one frame record including `imageUrl` (null when no image is stored). */
export function getSatelliteObservationById(id: string): Promise<ServiceResult<SatelliteObservation | null>> {
  return serve({ live: () => orNullOn404(apiGet<SatelliteObservation>(`/satellite/${encodeURIComponent(id)}`)) });
}

/** Timeline slots derived from the frames themselves (slotId, else the scan timestamp). */
function slotsFrom(observations: SatelliteObservation[]): SatelliteTimeSlot[] {
  const ids = [...new Set(observations.map((observation) => observation.slotId || observation.timestamp))].sort();
  return ids.map((id) => ({ id, label: `${id.slice(8, 10)}/${id.slice(5, 7)} ${id.slice(11, 16)}`, timestamp: id }));
}

/** Composite for the satellite workspace: sources + frame metadata + channel taxonomy + slots. */
export async function getSatelliteCatalog(selection: RegionSelection): Promise<ServiceResult<SatelliteCatalog>> {
  const [sources, observations] = await Promise.all([
    getSatelliteSources(selection),
    getSatelliteObservations({ regionId: selection.regionId, subregionId: selection.subregionId, pageSize: 1000 }),
  ]);
  return {
    source: "live",
    data: {
      regionId: selection.regionId,
      subregionId: selection.subregionId,
      availability: sources.data.availability,
      sources: sources.data.sources,
      channels: SATELLITE_CHANNELS,
      slots: slotsFrom(observations.data.items),
      observations: observations.data.items,
    },
  };
}

/** GET /api/satellite/latest?region=… — the dashboard's latest-frame card. */
export function getLatestSatelliteFrame(regionId = "north_indian_ocean"): Promise<ServiceResult<SatelliteFrame | null>> {
  return serve({ live: () => orNullOn404(apiGet<SatelliteFrame>("/satellite/latest", { region: regionId })) });
}
