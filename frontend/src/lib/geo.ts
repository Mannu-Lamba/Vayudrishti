import type { CoastalDistrict, CoastalImpact, GeoTrackPoint, RiskZoneSpec } from "@/types/track";
import type { MapBounds } from "@/types/region";

const KM_PER_DEG = 110.574;

export type Position = [number, number];

export function toPosition(point: { latitude: number; longitude: number }): Position {
  return [point.longitude, point.latitude];
}

export function lineString(points: GeoTrackPoint[]) {
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "LineString" as const, coordinates: points.map(toPosition) },
  };
}

export function pointCollection(points: GeoTrackPoint[]) {
  return {
    type: "FeatureCollection" as const,
    features: points.map((point) => ({
      type: "Feature" as const,
      properties: { ...point },
      geometry: { type: "Point" as const, coordinates: toPosition(point) },
    })),
  };
}

/** Approximate circle as a polygon ring — placeholder for real model risk polygons. */
export function circlePolygon(center: { latitude: number; longitude: number }, radiusKm: number, steps = 64): Position[] {
  const latDelta = radiusKm / KM_PER_DEG;
  const lngDelta = radiusKm / (KM_PER_DEG * Math.cos((center.latitude * Math.PI) / 180));
  const ring: Position[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const angle = (i / steps) * Math.PI * 2;
    ring.push([center.longitude + lngDelta * Math.cos(angle), center.latitude + latDelta * Math.sin(angle)]);
  }
  return ring;
}

export function riskCollection(zones: RiskZoneSpec[]) {
  return {
    type: "FeatureCollection" as const,
    features: zones.map((zone) => ({
      type: "Feature" as const,
      properties: {
        id: zone.id,
        level: zone.level,
        label: zone.label,
        radiusKm: zone.radiusKm,
        centerLat: zone.center.latitude,
        centerLng: zone.center.longitude,
      },
      geometry: { type: "Polygon" as const, coordinates: [circlePolygon(zone.center, zone.radiusKm)] },
    })),
  };
}

/** Great-circle distance in km between two lat/lng points (haversine). */
export function haversineKm(a: { latitude: number; longitude: number }, b: { latitude: number; longitude: number }): number {
  const R = 6371;
  const dLat = ((b.latitude - a.latitude) * Math.PI) / 180;
  const dLng = ((b.longitude - a.longitude) * Math.PI) / 180;
  const lat1 = (a.latitude * Math.PI) / 180;
  const lat2 = (b.latitude * Math.PI) / 180;
  const sinLat = Math.sin(dLat / 2);
  const sinLng = Math.sin(dLng / 2);
  const h = sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLng * sinLng;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Coastal districts whose centroid falls inside a risk zone's circle, nearest first. */
export function districtsInRiskZone(center: { latitude: number; longitude: number }, radiusKm: number, districts: CoastalDistrict[]): CoastalImpact[] {
  return districts
    .map((district) => ({ district, distanceKm: haversineKm(center, district) }))
    .filter((impact) => impact.distanceKm <= radiusKm)
    .sort((a, b) => a.distanceKm - b.distanceKm);
}

/** Dashed circle per forecast fix that carries an uncertainty radius. */
export function uncertaintyCircles(points: GeoTrackPoint[]) {
  return {
    type: "FeatureCollection" as const,
    features: points
      .filter((point) => point.uncertaintyRadiusKm)
      .map((point) => ({
        type: "Feature" as const,
        properties: { id: point.id, radiusKm: point.uncertaintyRadiusKm },
        geometry: { type: "Polygon" as const, coordinates: [circlePolygon(point, point.uncertaintyRadiusKm ?? 0, 48)] },
      })),
  };
}

export function polygonFeature(ring: Position[]) {
  return { type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates: [ring] } };
}

/**
 * Uncertainty corridor along the forecast path. With `widthsKm` (per-point radii from the
 * prediction) it follows those; otherwise it widens linearly from startKm to endKm.
 * The linear fallback is illustrative only — never presented as a model-derived cone.
 */
export function uncertaintyCorridor(points: GeoTrackPoint[], startKm: number, endKm: number, widthsKm?: (number | undefined)[]) {
  const left: Position[] = [];
  const right: Position[] = [];
  points.forEach((point, index) => {
    const next = points[index + 1] ?? points[index - 1] ?? point;
    const dx = next.longitude - point.longitude;
    const dy = next.latitude - point.latitude;
    const length = Math.hypot(dx, dy) || 1;
    const ratio = points.length > 1 ? index / (points.length - 1) : 0;
    const widthKm = widthsKm?.[index] ?? startKm + (endKm - startKm) * ratio;
    const latDelta = widthKm / KM_PER_DEG;
    const lngDelta = widthKm / (KM_PER_DEG * Math.cos((point.latitude * Math.PI) / 180));
    const nx = -dy / length;
    const ny = dx / length;
    left.push([point.longitude + nx * lngDelta, point.latitude + ny * latDelta]);
    right.push([point.longitude - nx * lngDelta, point.latitude - ny * latDelta]);
  });
  const ring = [...left, ...right.reverse()];
  if (ring.length) ring.push(ring[0]);
  return {
    type: "Feature" as const,
    properties: {},
    geometry: { type: "Polygon" as const, coordinates: [ring] },
  };
}

export const RISK_COLORS: Record<string, string> = {
  low: "#22d3ee",
  moderate: "#38bdf8",
  high: "#f59e0b",
  severe: "#ef4444",
};

export function formatCoords(latitude: number, longitude: number) {
  const lon = normalizeLon(longitude);
  const ns = latitude >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(latitude).toFixed(1)}° ${ns} / ${Math.abs(lon).toFixed(1)}° ${ew}`;
}

/** "12.4°S / 68.3°E" — compact form used in registry rows and readouts. */
export function formatCoordsCompact(latitude: number, longitude: number) {
  return `${formatLatitude(latitude)} / ${formatLongitude(longitude)}`;
}

export function formatLatitude(latitude: number) {
  return `${Math.abs(latitude).toFixed(1)}°${latitude >= 0 ? "N" : "S"}`;
}

export function formatLongitude(longitude: number) {
  const lon = normalizeLon(longitude);
  return `${Math.abs(lon).toFixed(1)}°${lon >= 0 ? "E" : "W"}`;
}

// ── Region bounds helpers (antimeridian-aware) ────────────────────────────

/** Wrap a longitude into (-180, 180]. */
export function normalizeLon(longitude: number) {
  const wrapped = ((((longitude + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 ? 180 : wrapped;
}

/** Longitude expressed in the frame that starts at `west`, so bounds with east > 180 compare correctly. */
export function lonInFrame(longitude: number, west: number) {
  return west + ((((longitude - west) % 360) + 360) % 360);
}

export function inBounds(bounds: MapBounds, latitude: number, longitude: number) {
  return latitude <= bounds.north && latitude >= bounds.south && lonInFrame(longitude, bounds.west) <= bounds.east;
}

/** Fractional position (0–1) of a point inside bounds — equirectangular, for placing overlays on imagery. */
export function projectToFrame(bounds: MapBounds, latitude: number, longitude: number) {
  return {
    x: (lonInFrame(longitude, bounds.west) - bounds.west) / (bounds.east - bounds.west),
    y: (bounds.north - latitude) / (bounds.north - bounds.south),
  };
}

export function boundsCenter(bounds: MapBounds) {
  return { latitude: (bounds.north + bounds.south) / 2, longitude: normalizeLon((bounds.west + bounds.east) / 2) };
}

export function boundsRing(bounds: MapBounds): Position[] {
  const { north, south, east, west } = bounds;
  return [[west, north], [east, north], [east, south], [west, south], [west, north]];
}

/** Linear interpolation along a track's fixes at `offsetHours` (clamped to the track's extent). */
export function interpolateTrack(points: GeoTrackPoint[], offsetHours: number) {
  if (!points.length) return null;
  const sorted = [...points].sort((a, b) => a.offsetHours - b.offsetHours);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (offsetHours <= first.offsetHours) return first;
  if (offsetHours >= last.offsetHours) return last;
  const nextIndex = sorted.findIndex((point) => point.offsetHours >= offsetHours);
  const b = sorted[nextIndex];
  const a = sorted[nextIndex - 1];
  const t = (offsetHours - a.offsetHours) / (b.offsetHours - a.offsetHours);
  const lerp = (x: number, y: number) => x + (y - x) * t;
  return {
    ...a,
    offsetHours,
    latitude: lerp(a.latitude, b.latitude),
    longitude: lerp(a.longitude, b.longitude),
    // Interpolate only between observed values; a missing value stays missing.
    windKmh: a.windKmh != null && b.windKmh != null ? Math.round(lerp(a.windKmh, b.windKmh)) : null,
    pressureHpa: a.pressureHpa != null && b.pressureHpa != null ? Math.round(lerp(a.pressureHpa, b.pressureHpa)) : null,
    confidence: a.confidence != null && b.confidence != null ? Math.round(lerp(a.confidence, b.confidence) * 10) / 10 : undefined,
  };
}
