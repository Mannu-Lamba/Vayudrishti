// Cyclone registry, tracks, history and regional observations.
import { historicalCyclones, mockArchiveSummary, mockCyclones } from "@/data/mock/cyclones";
import { mockOperationalEvents } from "@/data/mock/events";
import { mockGeoTracks, mockTrackResponses } from "@/data/mock/geotracks";
import { mockRegions } from "@/data/mock/regions";
import { interpolateTrack } from "@/lib/geo";
import { formatFixTime } from "@/lib/mapScene";
import { cycloneInSelection, resolveCycloneArea } from "@/lib/regions";
import { toIsoTimestamp } from "@/lib/time";
import { apiGet, orNullOn404 } from "./apiClient";
import { paginateDemo, serve } from "./dataMode";
import type { DateRangeQuery, PageQuery, Paginated, ServiceResult } from "@/types/api";
import type { ArchiveSummary, CycloneArchiveQuery, CycloneData, CycloneQuery, HistoricalCyclone, OperationalEvent } from "@/types/cyclone";
import type { ObservedSystem, RegionalCycloneObservation, RegionSelection } from "@/types/region";
import type { CycloneGeoTrack, CycloneTrackResponse, GeoTrackPoint, TrackPoint } from "@/types/track";

const NOW_UTC_MS = Date.UTC(2026, 8, 8, 14, 30);
const HOUR_MS = 3_600_000;
const enc = encodeURIComponent;
const regionQuery = (selection?: RegionSelection) => ({ region: selection?.regionId, subregion: selection?.subregionId });

/** Demo stand-in for the backend's filtering. The demo registry holds only currently tracked systems. */
function matchesQuery(cyclone: CycloneData, query: CycloneQuery): boolean {
  if (query.region && !cycloneInSelection(mockRegions, cyclone, { regionId: query.region, subregionId: query.subregion })) return false;
  if (query.basin && cyclone.basin !== query.basin) return false;
  const observed = Date.parse(toIsoTimestamp(cyclone.observedAt));
  if (query.startDate && observed < Date.parse(query.startDate)) return false;
  if (query.endDate && observed > Date.parse(query.endDate)) return false;
  return query.active !== false;
}

/**
 * GET /api/cyclones?region=…&subregion=…&basin=…&startDate=…&endDate=…&active=…
 * The backend maps IBTrACS basin + position onto region/subregion and returns only matching systems.
 */
export function getCyclones(query: CycloneQuery = {}): Promise<ServiceResult<CycloneData[]>> {
  return serve({
    demo: () => mockCyclones.filter((cyclone) => matchesQuery(cyclone, query)),
    live: () => apiGet<CycloneData[]>("/cyclones", { ...query }),
    demoLatencyMs: 150,
  });
}

/** GET /api/cyclones/{id} */
export function getCycloneById(id: string): Promise<ServiceResult<CycloneData | null>> {
  return serve({
    demo: () => mockCyclones.find((cyclone) => cyclone.id === id) ?? null,
    live: () => orNullOn404(apiGet<CycloneData>(`/cyclones/${enc(id)}`)),
  });
}

const percent = (value: number | undefined) => (value == null ? undefined : value <= 1 ? Math.round(value * 1000) / 10 : value);
const leadLabel = (hours: number) => (hours === 0 ? "NOW" : hours < 0 ? `T${hours}h` : `T+${hours}h`);

/**
 * Adapter from the track payload to the map's track model: drops unusable fixes, sorts by time,
 * measures lead time from the latest observation and builds display labels. Demo and live
 * responses both pass through here.
 */
export function normalizeTrack(response: CycloneTrackResponse): CycloneGeoTrack {
  const points = response.points
    .filter((point) => Number.isFinite(point.latitude) && Number.isFinite(point.longitude) && !Number.isNaN(Date.parse(point.timestamp)))
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  const observed = points.filter((point) => !point.forecast);
  const anchor = Date.parse(response.observedAt ?? observed[observed.length - 1]?.timestamp ?? points[0]?.timestamp ?? "");
  const toFix = (point: TrackPoint): GeoTrackPoint => {
    const hours = Number.isNaN(anchor) ? 0 : Math.round(((Date.parse(point.timestamp) - anchor) / HOUR_MS) * 10) / 10;
    return {
      id: `${response.cycloneId}-${point.forecast ? "f" : "h"}-${point.timestamp}`,
      label: leadLabel(hours),
      offsetHours: hours,
      timestamp: formatFixTime(point.timestamp),
      latitude: point.latitude,
      longitude: point.longitude,
      windKmh: point.windKmh,
      pressureHpa: point.pressureHpa,
      confidence: percent(point.confidence),
      category: point.category,
      forecast: Boolean(point.forecast),
      uncertaintyRadiusKm: point.uncertaintyRadiusKm,
    };
  };
  return {
    cycloneId: response.cycloneId,
    history: observed.map(toFix),
    forecast: points.filter((point) => point.forecast).map(toFix),
    // Display fallback for the corridor width, only used when forecast fixes carry no radius.
    uncertaintyKm: response.uncertaintyKm ?? { start: 60, end: 200 },
    riskZones: response.riskZones ?? [],
  };
}

/** GET /api/cyclones/{id}/track?start=…&end=… — bounded so long tracks are never loaded whole. */
export function getCycloneTrack(id: string, range: DateRangeQuery = {}): Promise<ServiceResult<CycloneGeoTrack | null>> {
  return serve({
    demo: () => {
      const response = mockTrackResponses[id];
      return response ? normalizeTrack(response) : null;
    },
    live: async () => {
      const response = await orNullOn404(apiGet<CycloneTrackResponse>(`/cyclones/${enc(id)}/track`, { start: range.start, end: range.end }));
      return response ? normalizeTrack(response) : null;
    },
    demoLatencyMs: 200,
  });
}

/** GET /api/cyclones/{id}/history?page=…&pageSize=…&start=…&end=… — observed fixes, paged. */
export function getCycloneHistory(id: string, query: PageQuery & DateRangeQuery = {}): Promise<ServiceResult<Paginated<GeoTrackPoint>>> {
  return serve({
    demo: () => paginateDemo(mockGeoTracks[id]?.history ?? [], query.page, query.pageSize),
    live: () => apiGet<Paginated<GeoTrackPoint>>(`/cyclones/${enc(id)}/history`, { page: query.page, pageSize: query.pageSize, start: query.start, end: query.end }),
  });
}

/** GET /api/cyclones/archive?region=…&year=…&page=… — historical reference systems, paged. */
export function getCycloneArchive(query: CycloneArchiveQuery = {}): Promise<ServiceResult<Paginated<HistoricalCyclone>>> {
  return serve({
    demo: () => paginateDemo(query.year ? historicalCyclones.filter((record) => record.year === query.year) : historicalCyclones, query.page, query.pageSize),
    live: () => apiGet<Paginated<HistoricalCyclone>>("/cyclones/archive", { region: query.region, subregion: query.subregion, year: query.year, page: query.page, pageSize: query.pageSize }),
  });
}

/** GET /api/cyclones/archive/summary — coverage + seasonal counts, aggregated by the backend. */
export function getArchiveSummary(): Promise<ServiceResult<ArchiveSummary>> {
  return serve({ demo: () => mockArchiveSummary, live: () => apiGet<ArchiveSummary>("/cyclones/archive/summary") });
}

/** GET /api/events?limit=… — operational event feed. */
export function getRecentEvents(limit = 10): Promise<ServiceResult<OperationalEvent[]>> {
  return serve({ demo: () => mockOperationalEvents.slice(0, limit), live: () => apiGet<OperationalEvent[]>("/events", { limit }) });
}

function demoRegionalObservation(selection: RegionSelection, at: string): RegionalCycloneObservation {
  const offsetHours = (Date.parse(at) - NOW_UTC_MS) / HOUR_MS;
  const systems: ObservedSystem[] = mockCyclones
    .filter((cyclone) => cycloneInSelection(mockRegions, cyclone, selection))
    .map((cyclone) => {
      const track = mockGeoTracks[cyclone.id];
      const fix = track ? interpolateTrack([...track.history, ...track.forecast], Number.isFinite(offsetHours) ? offsetHours : 0) : null;
      const area = resolveCycloneArea(mockRegions, cyclone);
      return {
        cycloneId: cyclone.id,
        code: cyclone.code,
        name: cyclone.name,
        category: cyclone.category,
        status: cyclone.status,
        riskLevel: cyclone.riskLevel,
        basin: cyclone.basin,
        regionId: area?.regionId ?? selection.regionId,
        subregionId: area?.subregionId,
        latitude: fix?.latitude ?? cyclone.location.latitude,
        longitude: fix?.longitude ?? cyclone.location.longitude,
        windKmh: fix?.windKmh ?? cyclone.windKmh,
        pressureHpa: fix?.pressureHpa ?? cyclone.pressureHpa,
        confidence: fix?.confidence ?? cyclone.detectionConfidence,
      };
    })
    .sort((a, b) => b.windKmh - a.windKmh);
  return { regionId: selection.regionId, subregionId: selection.subregionId, timestamp: at, activeSystems: systems.length, systems, strongest: systems[0] };
}

/** GET /api/cyclones/regional-observation?region=…&subregion=…&at=… — systems in a sector at one time. */
export function getRegionalObservation(selection: RegionSelection, at: string): Promise<ServiceResult<RegionalCycloneObservation>> {
  return serve({
    demo: () => demoRegionalObservation(selection, at),
    live: () => apiGet<RegionalCycloneObservation>("/cyclones/regional-observation", { ...regionQuery(selection), at }),
  });
}
