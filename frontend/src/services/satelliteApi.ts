// Satellite sources, observations and frames. Real imagery arrives via `imageUrl` from the API;
// in demo mode the service renders a watermarked placeholder instead.
import { SATELLITE_CHANNELS } from "@/config/satelliteChannels";
import { mockCyclones } from "@/data/mock/cyclones";
import { mockRegions } from "@/data/mock/regions";
import { mockSatelliteAvailability, mockSatelliteFrame, mockSatelliteObservations, mockSatelliteSources, mockTimeSlots } from "@/data/mock/satellite";
import { mockSatelliteImageUrl } from "@/data/mock/satelliteImagery";
import { describeSelection } from "@/lib/regions";
import { apiGet, orNullOn404 } from "./apiClient";
import { paginateDemo, serve } from "./dataMode";
import type { Paginated, ServiceResult } from "@/types/api";
import type { RegionSelection, SatelliteSource } from "@/types/region";
import type { SatelliteCatalog, SatelliteFrame, SatelliteObservation, SatelliteObservationQuery, SatelliteSourceCatalog, SatelliteTimeSlot } from "@/types/satellite";

const MOCK_FRAME_LATENCY_MS = 320;

/** GET /api/satellite/sources?region=…&subregion=… — which sources cover the sector, with tiers. */
export function getSatelliteSources(selection: RegionSelection): Promise<ServiceResult<SatelliteSourceCatalog>> {
  return serve({
    demo: () => {
      const availability = mockSatelliteAvailability.find((entry) => entry.regionId === selection.regionId && entry.subregionId === selection.subregionId) ?? null;
      const sources = (availability?.sources ?? [])
        .map((coverage) => mockSatelliteSources.find((source) => source.id === coverage.sourceId))
        .filter((source): source is SatelliteSource => Boolean(source));
      return { availability, sources };
    },
    live: () => apiGet<SatelliteSourceCatalog>("/satellite/sources", { region: selection.regionId, subregion: selection.subregionId }),
  });
}

/** GET /api/satellite?region=…&source=…&channel=…&start=…&end=…&page=… — frame metadata only, paged. */
export function getSatelliteObservations(query: SatelliteObservationQuery): Promise<ServiceResult<Paginated<SatelliteObservation>>> {
  return serve({
    demo: () => {
      const matches = mockSatelliteObservations.filter((observation) => observation.regionId === query.regionId
        && observation.subregionId === query.subregionId
        && (!query.source || observation.source === query.source)
        && (!query.channel || observation.channel === query.channel)
        && (!query.start || observation.timestamp >= query.start)
        && (!query.end || observation.timestamp <= query.end));
      return paginateDemo(matches, query.page, query.pageSize ?? 500);
    },
    live: () => apiGet<Paginated<SatelliteObservation>>("/satellite", {
      region: query.regionId, subregion: query.subregionId, source: query.source, channel: query.channel,
      start: query.start, end: query.end, page: query.page, pageSize: query.pageSize,
    }),
  });
}

/** GET /api/satellite/{id} — one frame including `imageUrl` (null when the frame is unknown). */
export function getSatelliteObservationById(id: string): Promise<ServiceResult<SatelliteObservation | null>> {
  return serve({
    demoLatencyMs: MOCK_FRAME_LATENCY_MS,
    demo: () => {
      const observation = mockSatelliteObservations.find((candidate) => candidate.id === id);
      if (!observation?.available) return observation ?? null;
      const imageUrl = mockSatelliteImageUrl(observation, {
        landmarks: describeSelection(mockRegions, { regionId: observation.regionId, subregionId: observation.subregionId }).landmarks,
        source: mockSatelliteSources.find((source) => source.id === observation.source),
        slotIndex: mockTimeSlots.findIndex((slot) => slot.id === observation.slotId),
        windById: Object.fromEntries(mockCyclones.map((cyclone) => [cyclone.id, cyclone.windKmh])),
      });
      return { ...observation, imageUrl };
    },
    live: () => orNullOn404(apiGet<SatelliteObservation>(`/satellite/${encodeURIComponent(id)}`)),
  });
}

/** Timeline slots derived from the frames themselves (slotId, else the scan timestamp). */
function slotsFrom(observations: SatelliteObservation[]): SatelliteTimeSlot[] {
  const ids = [...new Set(observations.map((observation) => observation.slotId || observation.timestamp))].sort();
  return ids.map((id) => ({ id, label: id.slice(11, 16), timestamp: id }));
}

/** Composite for the satellite workspace: sources + frame metadata + channel taxonomy + slots. */
export async function getSatelliteCatalog(selection: RegionSelection): Promise<ServiceResult<SatelliteCatalog>> {
  const [sources, observations] = await Promise.all([
    getSatelliteSources(selection),
    getSatelliteObservations({ regionId: selection.regionId, subregionId: selection.subregionId, pageSize: 1000 }),
  ]);
  return {
    source: sources.source === "live" && observations.source === "live" ? "live" : "demo",
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
  return serve({ demo: () => mockSatelliteFrame, live: () => orNullOn404(apiGet<SatelliteFrame>("/satellite/latest", { region: regionId })) });
}
