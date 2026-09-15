/** 0–1 score → "91%" or "94.7%" (one decimal only when it carries information). */
export function formatPercent(value: number | undefined | null, digits?: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  const percent = value * 100;
  if (digits != null) return `${percent.toFixed(digits)}%`;
  const rounded = Math.round(percent * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

/** A value the data does not hold is shown as "—", never as "null" or 0. */
export function orDash(value: string | number | null | undefined, suffix = ""): string {
  return value == null || value === "" ? "—" : `${value}${suffix}`;
}

/** ISO 8601 → "25 Aug 2026 · 18:00 UTC" (the year matters for historical storms); unparsable input is shown as given. */
export function formatObservedAt(value: string | null | undefined): string {
  if (!value) return "—";
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return value;
  const date = new Date(ms);
  const day = date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return `${day} · ${time} UTC`;
}

/** "NW at 14 km/h", or "—" when the motion is unknown (a storm with a single fix). */
export function formatMovement(direction: string | null | undefined, speedKmh: number | null | undefined): string {
  return direction ? `${direction} at ${speedKmh ?? "—"} km/h` : "—";
}

/** A difference with its sign, rounded to one decimal (a subtraction of two decimals is never shown as 0.8999999…). */
export function signed(value: number): string {
  const rounded = Math.round(value * 10) / 10 || 0; // `|| 0` turns -0 into 0
  return `${rounded > 0 ? "+" : ""}${rounded}`;
}
