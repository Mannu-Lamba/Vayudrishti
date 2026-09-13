import { inBounds, lonInFrame, normalizeLon, projectToFrame } from "@/lib/geo";
import type { MapBounds, RegionLandmark, SatelliteSource } from "@/types/region";
import type { SatelliteChannelId, SatelliteObservation } from "@/types/satellite";

// Procedural stand-in for satellite imagery. It is NOT derived from any observation: an SVG cloud
// field (feTurbulence) coloured per channel, vortices at the mock track positions, a lat/lon
// graticule and a watermark. Phase 4 replaces this with image URLs from /api/satellite.

const W = 1600;
const H = 900;

interface ChannelLook {
  /** Colour ramp from clear sky to the densest/coldest cloud. */
  ramp: string[];
  slope: number;
  intercept: number;
  frequencyScale: number;
  seedOffset: number;
  vortex: { shield: string; band: string; mid: string; core: string; eye: string };
}

const LOOKS: Record<SatelliteChannelId, ChannelLook> = {
  infrared: {
    ramp: ["#0b1622", "#1d2b38", "#3a4b58", "#728591", "#aebcc3", "#5fc6d3"],
    slope: 2.1, intercept: -0.8, frequencyScale: 1, seedOffset: 0,
    vortex: { shield: "#5fc6d3", band: "#9edde5", mid: "#f0c23a", core: "#e8563a", eye: "#2b2433" },
  },
  water_vapor: {
    ramp: ["#140e08", "#3a2b1a", "#6e6556", "#a7aba4", "#d9e4e6", "#f3fbfd"],
    slope: 1.7, intercept: -0.42, frequencyScale: 0.65, seedOffset: 17,
    vortex: { shield: "#dbe8eb", band: "#eef6f8", mid: "#ffffff", core: "#ffffff", eye: "#3a2b1a" },
  },
  visible: {
    ramp: ["#05080c", "#131a22", "#48505a", "#98a0a9", "#dde2e7", "#ffffff"],
    slope: 2.4, intercept: -0.95, frequencyScale: 1, seedOffset: 0,
    vortex: { shield: "#c9d0d6", band: "#e8ecef", mid: "#f4f6f8", core: "#ffffff", eye: "#1c2229" },
  },
};

const hexToUnit = (hex: string) => [1, 3, 5].map((index) => (parseInt(hex.slice(index, index + 2), 16) / 255).toFixed(3));

function rampTables(ramp: string[]) {
  const rgb = ramp.map(hexToUnit);
  return [0, 1, 2].map((channel) => rgb.map((color) => color[channel]).join(" "));
}

function hashSeed(text: string) {
  let hash = 7;
  for (const char of text) hash = (hash * 31 + char.charCodeAt(0)) % 9973;
  return (hash % 997) + 1;
}

const fmt = (value: number) => value.toFixed(1);

function graticule(bounds: MapBounds) {
  const lonSpan = bounds.east - bounds.west;
  const step = lonSpan >= 120 ? 20 : lonSpan >= 40 ? 10 : 5;
  const x = (lon: number) => ((lon - bounds.west) / lonSpan) * W;
  const y = (lat: number) => ((bounds.north - lat) / (bounds.north - bounds.south)) * H;
  const lines: string[] = [];
  const labels: string[] = [];
  for (let lat = Math.ceil(bounds.south / step) * step; lat <= bounds.north; lat += step) {
    lines.push(`M0 ${fmt(y(lat))}H${W}`);
    labels.push(`<text x="12" y="${fmt(y(lat) - 6)}">${Math.abs(lat)}°${lat > 0 ? "N" : lat < 0 ? "S" : ""}</text>`);
  }
  for (let lon = Math.ceil(bounds.west / step) * step; lon <= bounds.east; lon += step) {
    const wrapped = normalizeLon(lon);
    lines.push(`M${fmt(x(lon))} 0V${H}`);
    labels.push(`<text x="${fmt(x(lon) + 6)}" y="${H - 14}">${Math.abs(wrapped)}°${wrapped > 0 && wrapped < 180 ? "E" : wrapped < 0 ? "W" : ""}</text>`);
  }
  return `<path d="${lines.join("")}" stroke="#a9c4d6" stroke-opacity=".13" stroke-width="1" fill="none"/>
    <g fill="#bcd3e0" fill-opacity=".5" font-family="monospace" font-size="15">${labels.join("")}</g>`;
}

function spiralArms(radius: number) {
  const arms: string[] = [];
  for (let arm = 0; arm < 3; arm += 1) {
    const start = (arm * 2 * Math.PI) / 3;
    const points: string[] = [];
    for (let step = 0; step <= 40; step += 1) {
      const t = step / 40;
      const theta = start + t * 3.1 * Math.PI;
      const r = radius * (0.22 + 1.1 * t);
      points.push(`${fmt(r * Math.cos(theta))} ${fmt(r * Math.sin(theta))}`);
    }
    arms.push(`M${points.join("L")}`);
  }
  return arms;
}

interface VortexInput { x: number; y: number; radius: number; southern: boolean; rotation: number; strong: boolean; index: number }

function vortex(input: VortexInput, look: ChannelLook["vortex"]) {
  const { x, y, radius, southern, rotation, strong, index } = input;
  const id = `v${index}`;
  const arms = spiralArms(radius)
    .map((d, arm) => `<path d="${d}" fill="none" stroke="${look.band}" stroke-opacity="${0.55 - arm * 0.08}" stroke-width="${fmt(radius * (0.2 - arm * 0.03))}" stroke-linecap="round"/>`)
    .join("");
  const eye = strong
    ? `<circle r="${fmt(radius * 0.075)}" fill="${look.eye}"/><circle r="${fmt(radius * 0.12)}" fill="none" stroke="${look.core}" stroke-width="${fmt(radius * 0.05)}"/>`
    : "";
  return `<defs>
      <radialGradient id="${id}s"><stop offset="0" stop-color="${look.core}"/><stop offset=".22" stop-color="${look.mid}"/><stop offset=".5" stop-color="${look.shield}" stop-opacity=".85"/><stop offset="1" stop-color="${look.shield}" stop-opacity="0"/></radialGradient>
      <filter id="${id}b" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${fmt(radius * 0.06)}"/></filter>
    </defs>
    <g transform="translate(${fmt(x)} ${fmt(y)}) scale(1 ${southern ? -1 : 1}) rotate(${fmt(rotation)})" filter="url(#${id}b)">
      <circle r="${fmt(radius * 1.2)}" fill="url(#${id}s)" opacity=".8"/>${arms}<circle r="${fmt(radius * 0.4)}" fill="url(#${id}s)"/>
    </g>
    <g transform="translate(${fmt(x)} ${fmt(y)})">${eye}</g>`;
}

export interface MockImageContext {
  landmarks: RegionLandmark[];
  source?: SatelliteSource;
  slotIndex: number;
  /** Wind speed per cyclone id, used to size and shape each vortex. */
  windById: Record<string, number>;
}

function renderSvg(observation: SatelliteObservation, context: MockImageContext) {
  const bounds = observation.bounds ?? { north: 30, south: -2, west: 45, east: 100 };
  const look = LOOKS[observation.channel];
  const lonSpan = bounds.east - bounds.west;
  const latSpan = bounds.north - bounds.south;
  const seed = hashSeed(`${observation.regionId}/${observation.subregionId ?? "*"}`) + look.seedOffset;
  const frequency = Math.min(0.014, Math.max(0.003, 0.00012 * lonSpan)) * look.frequencyScale;
  const band = context.source?.channels[observation.channel];
  const blur = (band && band.resolutionKm >= 3 ? 1.2 : band && band.resolutionKm >= 2 ? 0.5 : 0) + (observation.coverageTier === "limb" ? 0.9 : 0);
  const [tableR, tableG, tableB] = rampTables(look.ramp);
  const frameMinutes = new Date(observation.timestamp).getUTCMinutes() + new Date(observation.timestamp).getUTCHours() * 60;
  const driftX = -frameMinutes * 0.55;
  const driftY = frameMinutes * 0.12;
  const pxPerDeg = (W / lonSpan + H / latSpan) / 2;

  const vortices = (observation.detections ?? []).map((detection, index) => {
    const position = projectToFrame(bounds, detection.latitude, detection.longitude);
    const wind = context.windById[detection.cycloneId] ?? 80;
    return vortex({
      x: position.x * W,
      y: position.y * H,
      radius: (2 + wind / 45) * pxPerDeg,
      southern: detection.latitude < 0,
      rotation: hashSeed(detection.cycloneId) - context.slotIndex * 7,
      strong: wind >= 118,
      index,
    }, look.vortex);
  }).join("");

  const landmarks = context.landmarks
    .filter((landmark) => inBounds(bounds, landmark.latitude, landmark.longitude))
    .map((landmark) => {
      const position = projectToFrame(bounds, landmark.latitude, landmark.longitude);
      return `<text x="${fmt(position.x * W)}" y="${fmt(position.y * H)}">${landmark.label}</text>`;
    })
    .join("");

  let limb = "";
  if (observation.coverageTier === "limb" && context.source) {
    const subLon = lonInFrame(context.source.subSatelliteLongitude, bounds.west);
    const limbOnRight = subLon < bounds.west + lonSpan / 2;
    limb = `<defs><linearGradient id="limb" x1="${limbOnRight ? 0 : 1}" x2="${limbOnRight ? 1 : 0}"><stop offset=".45" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".7"/></linearGradient></defs><rect width="${W}" height="${H}" fill="url(#limb)"/>`;
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
  <defs>
    <filter id="clouds" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">
      <feTurbulence type="fractalNoise" baseFrequency="${frequency.toFixed(4)} ${(frequency * 1.6).toFixed(4)}" numOctaves="5" seed="${seed}"/>
      <feColorMatrix type="matrix" values="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 0 0 0 0 1"/>
      <feComponentTransfer><feFuncR type="linear" slope="${look.slope}" intercept="${look.intercept}"/><feFuncG type="linear" slope="${look.slope}" intercept="${look.intercept}"/><feFuncB type="linear" slope="${look.slope}" intercept="${look.intercept}"/></feComponentTransfer>
      <feComponentTransfer><feFuncR type="table" tableValues="${tableR}"/><feFuncG type="table" tableValues="${tableG}"/><feFuncB type="table" tableValues="${tableB}"/></feComponentTransfer>
      ${blur ? `<feGaussianBlur stdDeviation="${blur}"/>` : ""}
    </filter>
  </defs>
  <rect width="${W}" height="${H}" fill="${look.ramp[0]}"/>
  <g transform="translate(${fmt(driftX)} ${fmt(driftY)})"><rect x="-1100" y="-400" width="${W + 2200}" height="${H + 800}" filter="url(#clouds)"/></g>
  ${vortices}
  ${graticule(bounds)}
  <g fill="#d7ecf5" fill-opacity=".4" font-family="monospace" font-size="17" letter-spacing="4" text-anchor="middle">${landmarks}</g>
  ${limb}
  <text x="${W - 16}" y="${H - 16}" fill="#ffffff" fill-opacity=".4" font-family="monospace" font-size="15" letter-spacing="2" text-anchor="end">VAYUDRISHTI MOCK RENDER · NOT OBSERVED DATA</text>
</svg>`;
}

const cache = new Map<string, string>();

/** Data URL for an available observation; memoised per frame id. */
export function mockSatelliteImageUrl(observation: SatelliteObservation, context: MockImageContext): string {
  const cached = cache.get(observation.id);
  if (cached) return cached;
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(renderSvg(observation, context))}`;
  cache.set(observation.id, url);
  return url;
}
