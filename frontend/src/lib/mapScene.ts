import type { DataSource } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";
import type { CyclonePrediction } from "@/types/prediction";
import type { CycloneGeoTrack, CycloneMapScene, GeoTrackPoint, MapCycloneMarker, MapDataStatus } from "@/types/track";

// Adapters from API payloads to what the map draws. The map only ever receives markers and a scene.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (value: number) => String(value).padStart(2, "0");

/** "09 Sep · 02:30 UTC" */
export function formatFixTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${pad(date.getUTCDate())} ${MONTHS[date.getUTCMonth()]} · ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

/**
 * Observed track only. Forecast fixes come exclusively from the prediction service
 * (sceneFromPrediction), so a cyclone without a prediction shows no forecast.
 */
export function sceneFromTrack(track: CycloneGeoTrack): CycloneMapScene | null {
  const current = track.history.find((point) => point.offsetHours === 0) ?? track.history[track.history.length - 1];
  if (!current) return null;
  return {
    cycloneId: track.cycloneId,
    currentPosition: current,
    historicalTrack: track.history,
    forecastPoints: [],
    uncertaintyKm: track.uncertaintyKm,
    riskZones: track.riskZones,
  };
}

/** Observed track (when available) + the prediction's forecast fixes, radii and polygon. */
export function sceneFromPrediction(prediction: CyclonePrediction, track?: CycloneGeoTrack | null): CycloneMapScene {
  const trackCurrent = track?.history.find((point) => point.offsetHours === 0);
  const detection = prediction.confidence.detection;
  const current: GeoTrackPoint = trackCurrent ?? {
    id: `${prediction.cycloneId}-now`,
    label: "NOW",
    offsetHours: 0,
    timestamp: formatFixTime(prediction.current.observedAt),
    latitude: prediction.current.latitude,
    longitude: prediction.current.longitude,
    windKmh: prediction.current.windKmh,
    pressureHpa: prediction.current.pressureHpa,
    confidence: detection == null ? undefined : Math.round(detection * 1000) / 10,
    category: prediction.current.category,
    forecast: false,
  };
  const forecastPoints: GeoTrackPoint[] = prediction.forecast.map((point) => ({
    id: point.id,
    label: point.label,
    offsetHours: point.hours,
    timestamp: formatFixTime(point.forecastTime),
    latitude: point.latitude,
    longitude: point.longitude,
    windKmh: point.windKmh,
    pressureHpa: point.pressureHpa,
    confidence: point.confidence == null ? undefined : Math.round(point.confidence * 1000) / 10,
    forecast: true,
    uncertaintyRadiusKm: point.uncertaintyRadiusKm,
  }));
  return {
    cycloneId: prediction.cycloneId,
    currentPosition: current,
    historicalTrack: track?.history.length ? track.history : [current],
    forecastPoints,
    uncertaintyKm: track?.uncertaintyKm ?? { start: 60, end: 200 },
    uncertaintyPolygon: prediction.uncertainty?.polygon,
    riskZones: track?.riskZones ?? [],
  };
}

/** One marker per registry entry, at its latest observed position. */
export function toMapMarkers(cyclones: CycloneData[]): MapCycloneMarker[] {
  return cyclones.map((cyclone) => ({
    id: cyclone.id,
    code: cyclone.code,
    name: cyclone.name,
    category: cyclone.category,
    status: cyclone.status,
    latitude: cyclone.location.latitude,
    longitude: cyclone.location.longitude,
    windKmh: cyclone.windKmh,
    pressureHpa: cyclone.pressureHpa,
    observedAt: cyclone.observedAt,
  }));
}

interface RequestState {
  loading: boolean;
  error: unknown;
  refetch: () => void;
}

/** Map overlay state: the registry request (markers) first, then the selected cyclone's track. */
export function mapStatusFor(registry?: RequestState, track?: RequestState): MapDataStatus | undefined {
  if (registry?.loading) return { loading: true, loadingLabel: "LOADING CYCLONE DATA" };
  if (registry?.error) return { error: registry.error, onRetry: registry.refetch };
  if (track?.loading) return { loading: true, loadingLabel: "LOADING TRACK" };
  if (track?.error) return { error: track.error, onRetry: track.refetch };
  return undefined;
}

/** Provenance line for forecast popups. */
export const forecastLabelFor = (source: DataSource | undefined) => (source === "live" ? "LIVE MODEL OUTPUT" : "DEMO / MOCK MODEL OUTPUT");
