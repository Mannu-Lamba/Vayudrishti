// Cyclone registry, tracks, history and archive — the real storms of MongoDB cyclone_database (and the held-out
// best tracks the API serves), through the FastAPI registry endpoints. No demo data.
import { formatFixTime } from "@/lib/mapScene";
import { apiGet, orNullOn404 } from "./apiClient";
import { serve } from "./dataMode";
import type { DateRangeQuery, PageQuery, Paginated, ServiceResult } from "@/types/api";
import type { ArchiveSummary, CycloneArchiveQuery, CycloneData, CycloneQuery, HistoricalCyclone, OperationalEvent } from "@/types/cyclone";
import type { RegionalCycloneObservation, RegionSelection } from "@/types/region";
import type { CycloneGeoTrack, CycloneTrackResponse, GeoTrackPoint, TrackPoint } from "@/types/track";

const HOUR_MS = 3_600_000;
const enc = encodeURIComponent;
const regionQuery = (selection?: RegionSelection) => ({ region: selection?.regionId, subregion: selection?.subregionId });

/** GET /api/cyclones?region=…&subregion=…&basin=…&startDate=…&endDate=…&active=… — newest first. */
export function getCyclones(query: CycloneQuery = {}): Promise<ServiceResult<CycloneData[]>> {
  return serve({ live: () => apiGet<CycloneData[]>("/cyclones", { ...query }) });
}

/** GET /api/cyclones/{id} */
export function getCycloneById(id: string): Promise<ServiceResult<CycloneData | null>> {
  return serve({ live: () => orNullOn404(apiGet<CycloneData>(`/cyclones/${enc(id)}`)) });
}

const percent = (value: number | undefined) => (value == null ? undefined : value <= 1 ? Math.round(value * 1000) / 10 : value);
const leadLabel = (hours: number) => (hours === 0 ? "NOW" : hours < 0 ? `T${hours}h` : `T+${hours}h`);

/**
 * Adapter from the track payload to the map's track model: drops unusable fixes, sorts by time,
 * measures lead time from the latest observation and builds display labels.
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
      windKmh: point.windKmh ?? null,
      pressureHpa: point.pressureHpa ?? null,
      confidence: percent(point.confidence),
      category: point.category ?? undefined,
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
    live: async () => {
      const response = await orNullOn404(apiGet<CycloneTrackResponse>(`/cyclones/${enc(id)}/track`, { start: range.start, end: range.end }));
      return response ? normalizeTrack(response) : null;
    },
  });
}

/** GET /api/cyclones/{id}/history?page=…&pageSize=…&start=…&end=… — observed fixes, paged. */
export function getCycloneHistory(id: string, query: PageQuery & DateRangeQuery = {}): Promise<ServiceResult<Paginated<GeoTrackPoint>>> {
  return serve({
    live: () => apiGet<Paginated<GeoTrackPoint>>(`/cyclones/${enc(id)}/history`, { page: query.page, pageSize: query.pageSize, start: query.start, end: query.end }),
  });
}

/** GET /api/cyclones/archive?region=…&year=…&page=… — the storm archive, paged. */
export function getCycloneArchive(query: CycloneArchiveQuery = {}): Promise<ServiceResult<Paginated<HistoricalCyclone>>> {
  return serve({
    live: () => apiGet<Paginated<HistoricalCyclone>>("/cyclones/archive", { region: query.region, subregion: query.subregion, year: query.year, page: query.page, pageSize: query.pageSize }),
  });
}

/** GET /api/cyclones/archive/summary — coverage + storms per season, aggregated by the backend. */
export function getArchiveSummary(): Promise<ServiceResult<ArchiveSummary>> {
  return serve({ live: () => apiGet<ArchiveSummary>("/cyclones/archive/summary") });
}

/** GET /api/events?limit=… — the latest storm observations recorded in the database. */
export function getRecentEvents(limit = 10): Promise<ServiceResult<OperationalEvent[]>> {
  return serve({ live: () => apiGet<OperationalEvent[]>("/events", { limit }) });
}

/** GET /api/cyclones/regional-observation?region=…&subregion=…&at=… — storms in a sector within ±3 h of a time. */
export function getRegionalObservation(selection: RegionSelection, at: string): Promise<ServiceResult<RegionalCycloneObservation>> {
  return serve({ live: () => apiGet<RegionalCycloneObservation>("/cyclones/regional-observation", { ...regionQuery(selection), at }) });
}
