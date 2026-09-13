import type { SatelliteBand, SatelliteCoverageTier } from "@/types/region";
import type { SatelliteChannelId, SatelliteUnavailableReason } from "@/types/satellite";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const pad = (value: number) => String(value).padStart(2, "0");

export const CHANNEL_IDS: SatelliteChannelId[] = ["visible", "infrared", "water_vapor"];
export const DEFAULT_CHANNEL: SatelliteChannelId = "infrared";

export function isChannelId(value: string | null | undefined): value is SatelliteChannelId {
  return CHANNEL_IDS.includes(value as SatelliteChannelId);
}

export const TIER_LABEL: Record<SatelliteCoverageTier, string> = {
  primary: "Primary view",
  secondary: "Oblique view",
  limb: "Limb view",
};

export const UNAVAILABLE_SHORT: Record<SatelliteUnavailableReason, string> = {
  local_night: "LOCAL NIGHT",
  scan_gap: "SCAN GAP",
  processing: "PROCESSING",
  no_coverage: "NO COVERAGE",
};

/** "08 SEP 2026 — 14:30 UTC" */
export function formatFrameTimestamp(iso: string | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return `${pad(date.getUTCDate())} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()} — ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

/** "14:30 UTC" */
export function formatUtcClock(iso: string | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

/** "TIR-1 · 10.8 µm" */
export function bandLabel(band: SatelliteBand | undefined) {
  return band ? `${band.band} · ${band.wavelengthUm} µm` : "—";
}
