import type { CycloneGeoTrack, CycloneTrackResponse, GeoTrackPoint, RiskZoneSpec } from "@/types/track";

// Phase 2 mock geospatial fixes. Replace with GET /api/cyclones/{id}/track responses in Phase 4.
export const mockGeoTracks: Record<string, CycloneGeoTrack> = {
  "vd-001": {
    cycloneId: "vd-001",
    history: [
      { id: "vd-001-h24", label: "T-24h", offsetHours: -24, timestamp: "07 Sep · 14:30 UTC", latitude: 13.4, longitude: 89.2, windKmh: 92, pressureHpa: 992, confidence: 96.1, forecast: false },
      { id: "vd-001-h18", label: "T-18h", offsetHours: -18, timestamp: "07 Sep · 20:30 UTC", latitude: 13.9, longitude: 88.5, windKmh: 100, pressureHpa: 988, confidence: 95.8, forecast: false },
      { id: "vd-001-h12", label: "T-12h", offsetHours: -12, timestamp: "08 Sep · 02:30 UTC", latitude: 14.5, longitude: 87.9, windKmh: 108, pressureHpa: 984, confidence: 95.2, forecast: false },
      { id: "vd-001-h06", label: "T-6h", offsetHours: -6, timestamp: "08 Sep · 08:30 UTC", latitude: 14.8, longitude: 87.6, windKmh: 113, pressureHpa: 981, confidence: 94.9, forecast: false },
      { id: "vd-001-now", label: "NOW", offsetHours: 0, timestamp: "08 Sep · 14:30 UTC", latitude: 15.2, longitude: 87.4, windKmh: 118, pressureHpa: 978, confidence: 94.7, forecast: false },
    ],
    forecast: [
      { id: "vd-001-f06", label: "T+6h", offsetHours: 6, timestamp: "08 Sep · 20:30 UTC", latitude: 15.8, longitude: 86.8, windKmh: 124, pressureHpa: 973, confidence: 91.4, forecast: true },
      { id: "vd-001-f12", label: "T+12h", offsetHours: 12, timestamp: "09 Sep · 02:30 UTC", latitude: 16.4, longitude: 86.2, windKmh: 131, pressureHpa: 969, confidence: 88.2, forecast: true },
      { id: "vd-001-f18", label: "T+18h", offsetHours: 18, timestamp: "09 Sep · 08:30 UTC", latitude: 17.0, longitude: 85.6, windKmh: 135, pressureHpa: 965, confidence: 84.7, forecast: true },
      { id: "vd-001-f24", label: "T+24h", offsetHours: 24, timestamp: "09 Sep · 14:30 UTC", latitude: 17.6, longitude: 85.0, windKmh: 138, pressureHpa: 960, confidence: 81.3, forecast: true },
    ],
    uncertaintyKm: { start: 60, end: 220 },
    riskZones: [
      { id: "vd-001-severe", level: "severe", radiusKm: 130, center: { latitude: 15.2, longitude: 87.4 }, label: "Core wind field" },
      { id: "vd-001-high", level: "high", radiusKm: 260, center: { latitude: 16.3, longitude: 86.3 }, label: "Gale warning band" },
      { id: "vd-001-moderate", level: "moderate", radiusKm: 400, center: { latitude: 17.4, longitude: 85.2 }, label: "Coastal watch — north Andhra" },
    ],
  },
  "vd-002": {
    cycloneId: "vd-002",
    history: [
      { id: "vd-002-h18", label: "T-18h", offsetHours: -18, timestamp: "07 Sep · 20:00 UTC", latitude: 12.2, longitude: 67.4, windKmh: 58, pressureHpa: 1000, confidence: 90.4, forecast: false },
      { id: "vd-002-h12", label: "T-12h", offsetHours: -12, timestamp: "08 Sep · 02:00 UTC", latitude: 12.4, longitude: 66.6, windKmh: 64, pressureHpa: 998, confidence: 89.6, forecast: false },
      { id: "vd-002-h06", label: "T-6h", offsetHours: -6, timestamp: "08 Sep · 08:00 UTC", latitude: 12.6, longitude: 65.8, windKmh: 70, pressureHpa: 996, confidence: 88.9, forecast: false },
      { id: "vd-002-now", label: "NOW", offsetHours: 0, timestamp: "08 Sep · 14:00 UTC", latitude: 12.8, longitude: 65.1, windKmh: 74, pressureHpa: 994, confidence: 88.2, forecast: false },
    ],
    forecast: [
      { id: "vd-002-f06", label: "T+6h", offsetHours: 6, timestamp: "08 Sep · 20:00 UTC", latitude: 13.0, longitude: 64.2, windKmh: 79, pressureHpa: 992, confidence: 85.1, forecast: true },
      { id: "vd-002-f12", label: "T+12h", offsetHours: 12, timestamp: "09 Sep · 02:00 UTC", latitude: 13.1, longitude: 63.2, windKmh: 84, pressureHpa: 990, confidence: 82.6, forecast: true },
      { id: "vd-002-f24", label: "T+24h", offsetHours: 24, timestamp: "09 Sep · 14:00 UTC", latitude: 13.4, longitude: 61.4, windKmh: 88, pressureHpa: 988, confidence: 77.9, forecast: true },
    ],
    uncertaintyKm: { start: 70, end: 250 },
    riskZones: [
      { id: "vd-002-high", level: "high", radiusKm: 140, center: { latitude: 12.8, longitude: 65.1 }, label: "Core wind field" },
      { id: "vd-002-moderate", level: "moderate", radiusKm: 300, center: { latitude: 13.1, longitude: 63.4 }, label: "Shipping advisory band" },
    ],
  },
  "vd-003": {
    cycloneId: "vd-003",
    history: [
      { id: "vd-003-h12", label: "T-12h", offsetHours: -12, timestamp: "08 Sep · 01:45 UTC", latitude: 5.2, longitude: 92.8, windKmh: 37, pressureHpa: 1006, confidence: 83.5, forecast: false },
      { id: "vd-003-h06", label: "T-6h", offsetHours: -6, timestamp: "08 Sep · 07:45 UTC", latitude: 5.5, longitude: 92.2, windKmh: 42, pressureHpa: 1004, confidence: 82.4, forecast: false },
      { id: "vd-003-now", label: "NOW", offsetHours: 0, timestamp: "08 Sep · 13:45 UTC", latitude: 5.8, longitude: 91.6, windKmh: 46, pressureHpa: 1002, confidence: 81.9, forecast: false },
    ],
    forecast: [
      { id: "vd-003-f06", label: "T+6h", offsetHours: 6, timestamp: "08 Sep · 19:45 UTC", latitude: 6.2, longitude: 92.4, windKmh: 50, pressureHpa: 1001, confidence: 78.2, forecast: true },
      { id: "vd-003-f12", label: "T+12h", offsetHours: 12, timestamp: "09 Sep · 01:45 UTC", latitude: 6.7, longitude: 93.2, windKmh: 54, pressureHpa: 999, confidence: 74.6, forecast: true },
    ],
    uncertaintyKm: { start: 80, end: 210 },
    riskZones: [
      { id: "vd-003-moderate", level: "moderate", radiusKm: 120, center: { latitude: 5.8, longitude: 91.6 }, label: "Core wind field" },
      { id: "vd-003-low", level: "low", radiusKm: 260, center: { latitude: 6.5, longitude: 92.8 }, label: "Andaman sea watch" },
    ],
  },
};

// ── Phase 3 multi-region tracks, generated from a fix + steady motion ─────

const NOW_UTC_MS = Date.UTC(2026, 8, 8, 14, 30);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (value: number) => String(value).padStart(2, "0");
const round1 = (value: number) => Math.round(value * 10) / 10;

interface MockTrackSpec {
  cycloneId: string;
  now: { latitude: number; longitude: number; windKmh: number; pressureHpa: number; confidence: number };
  /** Motion and intensity change per 6 hours. */
  per6h: { dLat: number; dLon: number; dWind: number; dPressure: number };
  history: number[];
  forecast: number[];
  uncertaintyKm: { start: number; end: number };
  riskZones: RiskZoneSpec[];
}

function buildMockTrack(spec: MockTrackSpec): CycloneGeoTrack {
  const { cycloneId, now, per6h } = spec;
  const fix = (hours: number): GeoTrackPoint => {
    const steps = hours / 6;
    const time = new Date(NOW_UTC_MS + hours * 3_600_000);
    return {
      id: hours === 0 ? `${cycloneId}-now` : `${cycloneId}-${hours < 0 ? "h" : "f"}${pad(Math.abs(hours))}`,
      label: hours === 0 ? "NOW" : hours < 0 ? `T${hours}h` : `T+${hours}h`,
      offsetHours: hours,
      timestamp: `${pad(time.getUTCDate())} ${MONTHS[time.getUTCMonth()]} · ${pad(time.getUTCHours())}:${pad(time.getUTCMinutes())} UTC`,
      latitude: round1(now.latitude + per6h.dLat * steps),
      longitude: round1(now.longitude + per6h.dLon * steps),
      windKmh: Math.round(now.windKmh + per6h.dWind * steps),
      pressureHpa: Math.round(now.pressureHpa + per6h.dPressure * steps),
      // Past fixes were analysed with more data; forecast confidence decays with lead time.
      confidence: round1(hours <= 0 ? Math.min(99, now.confidence - 0.3 * steps) : now.confidence - 3.1 * steps),
      forecast: hours > 0,
    };
  };
  return {
    cycloneId,
    history: [...spec.history, 0].map(fix),
    forecast: spec.forecast.map(fix),
    uncertaintyKm: spec.uncertaintyKm,
    riskZones: spec.riskZones,
  };
}

const regionalTracks = [
  buildMockTrack({
    cycloneId: "vd-004",
    now: { latitude: -12.4, longitude: 68.3, windKmh: 75, pressureHpa: 993, confidence: 86.4 },
    per6h: { dLat: -0.35, dLon: -0.8, dWind: 4, dPressure: -2 },
    history: [-24, -18, -12, -6],
    forecast: [6, 12, 18, 24],
    uncertaintyKm: { start: 70, end: 230 },
    riskZones: [
      { id: "vd-004-high", level: "high", radiusKm: 120, center: { latitude: -12.4, longitude: 68.3 }, label: "Core wind field" },
      { id: "vd-004-moderate", level: "moderate", radiusKm: 280, center: { latitude: -13.1, longitude: 66.7 }, label: "Shipping advisory band" },
    ],
  }),
  buildMockTrack({
    cycloneId: "vd-005",
    now: { latitude: 18.6, longitude: 132.4, windKmh: 150, pressureHpa: 955, confidence: 96.2 },
    per6h: { dLat: 0.55, dLon: -0.75, dWind: 5, dPressure: -3 },
    history: [-24, -18, -12, -6],
    forecast: [6, 12, 18, 24],
    uncertaintyKm: { start: 60, end: 210 },
    riskZones: [
      { id: "vd-005-severe", level: "severe", radiusKm: 150, center: { latitude: 18.6, longitude: 132.4 }, label: "Core wind field" },
      { id: "vd-005-high", level: "high", radiusKm: 300, center: { latitude: 19.7, longitude: 130.9 }, label: "Gale warning band" },
      { id: "vd-005-moderate", level: "moderate", radiusKm: 460, center: { latitude: 20.8, longitude: 129.4 }, label: "Ryukyu Islands watch" },
    ],
  }),
  buildMockTrack({
    cycloneId: "vd-006",
    now: { latitude: 24.1, longitude: 146.8, windKmh: 100, pressureHpa: 985, confidence: 90.1 },
    per6h: { dLat: 0.7, dLon: 0.15, dWind: 3, dPressure: -2 },
    history: [-18, -12, -6],
    forecast: [6, 12, 24],
    uncertaintyKm: { start: 70, end: 240 },
    riskZones: [
      { id: "vd-006-high", level: "high", radiusKm: 130, center: { latitude: 24.1, longitude: 146.8 }, label: "Core wind field" },
      { id: "vd-006-moderate", level: "moderate", radiusKm: 280, center: { latitude: 25.5, longitude: 147.1 }, label: "Shipping advisory band" },
    ],
  }),
  buildMockTrack({
    cycloneId: "vd-007",
    now: { latitude: 12.3, longitude: 158.9, windKmh: 70, pressureHpa: 998, confidence: 84 },
    per6h: { dLat: 0.2, dLon: -0.95, dWind: 3, dPressure: -1.5 },
    history: [-12, -6],
    forecast: [6, 12, 18],
    uncertaintyKm: { start: 80, end: 220 },
    riskZones: [
      { id: "vd-007-moderate", level: "moderate", radiusKm: 110, center: { latitude: 12.3, longitude: 158.9 }, label: "Core wind field" },
      { id: "vd-007-low", level: "low", radiusKm: 240, center: { latitude: 12.7, longitude: 157 }, label: "Micronesia watch" },
    ],
  }),
  buildMockTrack({
    cycloneId: "vd-008",
    now: { latitude: 16.8, longitude: -112.5, windKmh: 165, pressureHpa: 958, confidence: 95 },
    per6h: { dLat: 0.25, dLon: -0.9, dWind: 2, dPressure: -1 },
    history: [-24, -18, -12, -6],
    forecast: [6, 12, 18, 24],
    uncertaintyKm: { start: 60, end: 200 },
    riskZones: [
      { id: "vd-008-severe", level: "severe", radiusKm: 140, center: { latitude: 16.8, longitude: -112.5 }, label: "Core wind field" },
      { id: "vd-008-high", level: "high", radiusKm: 290, center: { latitude: 17.3, longitude: -114.3 }, label: "Gale warning band" },
      { id: "vd-008-moderate", level: "moderate", radiusKm: 430, center: { latitude: 17.8, longitude: -116.1 }, label: "Revillagigedo Islands watch" },
    ],
  }),
  buildMockTrack({
    cycloneId: "vd-009",
    now: { latitude: 13.2, longitude: -128.9, windKmh: 65, pressureHpa: 1000, confidence: 82.7 },
    per6h: { dLat: 0.05, dLon: -1.2, dWind: 2, dPressure: -1 },
    history: [-12, -6],
    forecast: [6, 12],
    uncertaintyKm: { start: 80, end: 200 },
    riskZones: [
      { id: "vd-009-moderate", level: "moderate", radiusKm: 100, center: { latitude: 13.2, longitude: -128.9 }, label: "Core wind field" },
      { id: "vd-009-low", level: "low", radiusKm: 220, center: { latitude: 13.3, longitude: -131.3 }, label: "Open-ocean advisory" },
    ],
  }),
];

for (const track of regionalTracks) mockGeoTracks[track.cycloneId] = track;

export function geoTrackFor(cycloneId: string): CycloneGeoTrack {
  return mockGeoTracks[cycloneId] ?? mockGeoTracks["vd-001"];
}

// ── Demo payloads for GET /api/cyclones/{id}/track ─────────────────────
// Shaped exactly like the API response (ISO timestamps, measured values only) so demo and live
// tracks go through the same cycloneApi.normalizeTrack adapter. Observed fixes only: forecasts
// come from the prediction service, so a cyclone without a prediction shows no forecast.

const MOCK_YEAR = new Date(NOW_UTC_MS).getUTCFullYear();

/** "08 Sep · 14:30 UTC" → ISO 8601. */
function isoFromFixTime(label: string): string {
  const match = /(\d{2}) (\w{3}) · (\d{2}):(\d{2})/.exec(label);
  if (!match) return new Date(NOW_UTC_MS).toISOString();
  return new Date(Date.UTC(MOCK_YEAR, MONTHS.indexOf(match[2]), Number(match[1]), Number(match[3]), Number(match[4]))).toISOString();
}

function toTrackResponse(track: CycloneGeoTrack): CycloneTrackResponse {
  const current = track.history.find((point) => point.offsetHours === 0) ?? track.history[track.history.length - 1];
  return {
    cycloneId: track.cycloneId,
    observedAt: current ? isoFromFixTime(current.timestamp) : undefined,
    points: track.history.map((point) => ({
      timestamp: isoFromFixTime(point.timestamp),
      latitude: point.latitude,
      longitude: point.longitude,
      windKmh: point.windKmh,
      pressureHpa: point.pressureHpa,
      confidence: point.confidence,
    })),
    uncertaintyKm: track.uncertaintyKm,
    riskZones: track.riskZones,
  };
}

export const mockTrackResponses: Record<string, CycloneTrackResponse> = Object.fromEntries(
  Object.entries(mockGeoTracks).map(([cycloneId, track]) => [cycloneId, toTrackResponse(track)]),
);
