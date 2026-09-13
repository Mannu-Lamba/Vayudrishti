import { mockCyclones } from "./cyclones";
import { geoTrackFor } from "./geotracks";
import { mockRegions } from "./regions";
import { boundsCenter, inBounds, interpolateTrack } from "@/lib/geo";
import { describeSelection } from "@/lib/regions";
import { SATELLITE_CHANNELS } from "@/config/satelliteChannels";
import type { MapBounds, SatelliteAvailability, SatelliteSource } from "@/types/region";
import type { SatelliteChannelSpec, SatelliteDetection, SatelliteFrame, SatelliteObservation, SatelliteTimeSlot } from "@/types/satellite";

// Phase 1 dashboard card frame.
export const mockSatelliteFrame: SatelliteFrame = {
  id: "insat3d-ir-20260908-1430",
  source: "IMD / MOSDAC",
  satellite: "INSAT-3D",
  channel: "Infrared",
  capturedAt: "08 Sep 2026 · 14:30 UTC",
  status: "processed",
  region: "North Indian Ocean",
  resolutionKm: 4,
  cloudTopTemperature: "−68°C core",
  enhancement: "BD enhancement curve",
};

// ── Phase 3: sources, channels, regional availability, observations ───────
// Instrument facts (bands, nominal resolution, cadence, slots) are indicative; every frame,
// status and detection below is mock. Phase 4: GET /api/satellite and /api/satellite/{source}.

const IMAGER_BANDS: SatelliteSource["channels"] = {
  visible: { band: "VIS", wavelengthUm: 0.65, resolutionKm: 1 },
  infrared: { band: "TIR-1", wavelengthUm: 10.8, resolutionKm: 4 },
  water_vapor: { band: "WV", wavelengthUm: 6.8, resolutionKm: 8 },
};

const ABI_BANDS: SatelliteSource["channels"] = {
  visible: { band: "C02", wavelengthUm: 0.64, resolutionKm: 0.5 },
  infrared: { band: "C13", wavelengthUm: 10.3, resolutionKm: 2 },
  water_vapor: { band: "C08", wavelengthUm: 6.2, resolutionKm: 2 },
};

export const mockSatelliteSources: SatelliteSource[] = [
  { id: "insat-3d", name: "INSAT-3D", family: "INSAT", agency: "ISRO / IMD", dataProvider: "MOSDAC", instrument: "Imager (6-channel)", subSatelliteLongitude: 82, cadenceMinutes: 30, channels: IMAGER_BANDS },
  { id: "insat-3dr", name: "INSAT-3DR", family: "INSAT", agency: "ISRO / IMD", dataProvider: "MOSDAC", instrument: "Imager (6-channel)", subSatelliteLongitude: 74, cadenceMinutes: 30, channels: IMAGER_BANDS },
  { id: "insat-3ds", name: "INSAT-3DS", family: "INSAT", agency: "ISRO / IMD", dataProvider: "MOSDAC", instrument: "Imager (6-channel)", subSatelliteLongitude: 82, cadenceMinutes: 30, channels: IMAGER_BANDS },
  {
    id: "himawari-9", name: "Himawari-9", family: "Himawari", agency: "JMA", dataProvider: "JMA / JAXA", instrument: "AHI", subSatelliteLongitude: 140.7, cadenceMinutes: 10,
    channels: {
      visible: { band: "B03", wavelengthUm: 0.64, resolutionKm: 0.5 },
      infrared: { band: "B13", wavelengthUm: 10.4, resolutionKm: 2 },
      water_vapor: { band: "B08", wavelengthUm: 6.2, resolutionKm: 2 },
    },
  },
  { id: "goes-18", name: "GOES-18", family: "GOES", agency: "NOAA", dataProvider: "NOAA NESDIS", instrument: "ABI", serviceSlot: "GOES-West", subSatelliteLongitude: -137.2, cadenceMinutes: 10, channels: ABI_BANDS },
  { id: "goes-19", name: "GOES-19", family: "GOES", agency: "NOAA", dataProvider: "NOAA NESDIS", instrument: "ABI", serviceSlot: "GOES-East", subSatelliteLongitude: -75.2, cadenceMinutes: 10, channels: ABI_BANDS },
  {
    id: "meteosat-9", name: "Meteosat-9", family: "Meteosat", agency: "EUMETSAT", dataProvider: "EUMETSAT Data Store", instrument: "SEVIRI", serviceSlot: "IODC", subSatelliteLongitude: 45.5, cadenceMinutes: 15,
    channels: {
      visible: { band: "VIS0.6", wavelengthUm: 0.6, resolutionKm: 3 },
      infrared: { band: "IR10.8", wavelengthUm: 10.8, resolutionKm: 3 },
      water_vapor: { band: "WV6.2", wavelengthUm: 6.2, resolutionKm: 3 },
    },
  },
];

const mockSatelliteChannels: SatelliteChannelSpec[] = SATELLITE_CHANNELS;

// Which sources see which sector. Tiers follow viewing geometry from each sub-satellite point.
export const mockSatelliteAvailability: SatelliteAvailability[] = [
  {
    regionId: "north_indian_ocean", defaultSourceId: "insat-3d",
    sources: [
      { sourceId: "insat-3d", tier: "primary" },
      { sourceId: "insat-3dr", tier: "primary" },
      { sourceId: "insat-3ds", tier: "primary" },
      { sourceId: "meteosat-9", tier: "secondary", note: "IODC slot at 45.5°E" },
      { sourceId: "himawari-9", tier: "limb", note: "Eastern Bay of Bengal only — oblique view" },
    ],
  },
  {
    regionId: "north_indian_ocean", subregionId: "arabian_sea", defaultSourceId: "insat-3d",
    sources: [
      { sourceId: "insat-3d", tier: "primary" },
      { sourceId: "insat-3dr", tier: "primary" },
      { sourceId: "insat-3ds", tier: "primary" },
      { sourceId: "meteosat-9", tier: "primary", note: "IODC slot at 45.5°E" },
    ],
  },
  {
    regionId: "north_indian_ocean", subregionId: "bay_of_bengal", defaultSourceId: "insat-3d",
    sources: [
      { sourceId: "insat-3d", tier: "primary" },
      { sourceId: "insat-3dr", tier: "primary" },
      { sourceId: "insat-3ds", tier: "primary" },
      { sourceId: "himawari-9", tier: "secondary", note: "Western edge of the Himawari disk" },
      { sourceId: "meteosat-9", tier: "secondary", note: "Eastern edge of the IODC disk" },
    ],
  },
  {
    regionId: "south_indian_ocean", defaultSourceId: "meteosat-9",
    sources: [
      { sourceId: "meteosat-9", tier: "primary", note: "RSMC La Réunion operational source" },
      { sourceId: "insat-3d", tier: "primary" },
      { sourceId: "insat-3dr", tier: "primary" },
      { sourceId: "himawari-9", tier: "limb", note: "East of 100°E only" },
    ],
  },
  {
    regionId: "pacific_ocean", defaultSourceId: "himawari-9",
    sources: [
      { sourceId: "himawari-9", tier: "primary", note: "Western half of the overview" },
      { sourceId: "goes-18", tier: "primary", note: "Central and eastern half of the overview" },
      { sourceId: "goes-19", tier: "limb", note: "Eastern margin only" },
    ],
  },
  {
    regionId: "pacific_ocean", subregionId: "western_pacific", defaultSourceId: "himawari-9",
    sources: [
      { sourceId: "himawari-9", tier: "primary" },
      { sourceId: "goes-18", tier: "limb", note: "East of 150°E only" },
    ],
  },
  {
    regionId: "pacific_ocean", subregionId: "eastern_pacific", defaultSourceId: "goes-18",
    sources: [
      { sourceId: "goes-18", tier: "primary" },
      { sourceId: "goes-19", tier: "secondary", note: "Mexican coast and eastern sector" },
    ],
  },
  {
    regionId: "pacific_ocean", subregionId: "southern_pacific", defaultSourceId: "himawari-9",
    sources: [
      { sourceId: "himawari-9", tier: "primary", note: "Coral Sea to Fiji" },
      { sourceId: "goes-18", tier: "secondary", note: "East of 170°E" },
    ],
  },
];

const NOW_UTC_MS = Date.UTC(2026, 8, 8, 14, 30);
const SLOT_OFFSETS_MINUTES = [-180, -150, -120, -90, -60, -30, 0];
const pad = (value: number) => String(value).padStart(2, "0");
const hhmm = (ms: number) => new Date(ms).toISOString().slice(11, 16);

export const mockTimeSlots: SatelliteTimeSlot[] = SLOT_OFFSETS_MINUTES.map((minutes) => {
  const iso = new Date(NOW_UTC_MS + minutes * 60_000).toISOString();
  return { id: iso, label: iso.slice(11, 16), timestamp: iso };
});

/** Scan start relative to the nominal slot — e.g. Himawari's 14:20 full disk is filed under 14:30. */
const FRAME_OFFSET_MINUTES: Record<string, number> = {
  "insat-3d": 0, "insat-3dr": -15, "insat-3ds": 0, "himawari-9": -10, "goes-18": -10, "goes-19": 0, "meteosat-9": 0,
};

// Deterministic demo gaps so the unavailable/processing states are reachable.
const SCAN_GAPS = new Set(["insat-3dr@13:00", "goes-19@12:30"]);
const STILL_PROCESSING = new Set(["insat-3ds@14:30"]);

function localSolarHours(utcMs: number, longitude: number) {
  const utcHours = new Date(utcMs).getUTCHours() + new Date(utcMs).getUTCMinutes() / 60;
  return (((utcHours + longitude / 15) % 24) + 24) % 24;
}

const formatHours = (hours: number) => `${pad(Math.floor(hours))}:${pad(Math.floor((hours % 1) * 60))}`;

/** Systems inside the frame at scan time, positioned by interpolating each mock track. */
function detectionsAt(bounds: MapBounds, frameMs: number): SatelliteDetection[] {
  const offsetHours = (frameMs - NOW_UTC_MS) / 3_600_000;
  return mockCyclones.flatMap((cyclone) => {
    const track = geoTrackFor(cyclone.id);
    const fix = interpolateTrack([...track.history, ...track.forecast], offsetHours);
    if (!fix || !inBounds(bounds, fix.latitude, fix.longitude)) return [];
    return [{ cycloneId: cyclone.id, code: cyclone.code, latitude: fix.latitude, longitude: fix.longitude, confidence: fix.confidence ?? cyclone.detectionConfidence }];
  });
}

function buildObservations(): SatelliteObservation[] {
  const observations: SatelliteObservation[] = [];
  for (const availability of mockSatelliteAvailability) {
    const selection = { regionId: availability.regionId, subregionId: availability.subregionId };
    const view = describeSelection(mockRegions, selection);
    const center = boundsCenter(view.bounds);
    for (const coverage of availability.sources) {
      const source = mockSatelliteSources.find((candidate) => candidate.id === coverage.sourceId);
      if (!source) continue;
      for (const channel of mockSatelliteChannels) {
        const band = source.channels[channel.id];
        if (!band) continue;
        for (const slot of mockTimeSlots) {
          const frameMs = Date.parse(slot.timestamp) + (FRAME_OFFSET_MINUTES[source.id] ?? 0) * 60_000;
          const solar = localSolarHours(frameMs, center.longitude);
          const key = `${source.id}@${slot.label}`;
          const base: SatelliteObservation = {
            id: `${source.id}-${channel.id}-${availability.subregionId ?? availability.regionId}-${hhmm(Date.parse(slot.timestamp)).replace(":", "")}`,
            regionId: availability.regionId,
            subregionId: availability.subregionId,
            source: source.id,
            channel: channel.id,
            timestamp: new Date(frameMs).toISOString(),
            slotId: slot.id,
            bounds: view.bounds,
            coverage: `${view.label} sector`,
            coverageTier: coverage.tier,
            resolution: coverage.tier === "limb" ? `${band.resolutionKm} km nadir · degraded at limb` : `${band.resolutionKm} km`,
            localSolarTime: formatHours(solar),
            available: false,
          };
          if (SCAN_GAPS.has(key)) {
            observations.push({ ...base, processingStatus: "missing", unavailableReason: "scan_gap" });
          } else if (STILL_PROCESSING.has(key)) {
            observations.push({ ...base, processingStatus: "processing", processingLevel: "L1B received", unavailableReason: "processing" });
          } else if (channel.requiresDaylight && (solar < 6.5 || solar >= 17.5)) {
            observations.push({ ...base, processingStatus: "processed", processingLevel: "L1C", unavailableReason: "local_night" });
          } else {
            observations.push({ ...base, available: true, processingStatus: "processed", processingLevel: "L1C (mock)", detections: detectionsAt(view.bounds, frameMs) });
          }
        }
      }
    }
  }
  return observations;
}

export const mockSatelliteObservations = buildObservations();
