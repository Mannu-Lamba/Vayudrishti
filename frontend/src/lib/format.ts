/** 0–1 score → "91%" or "94.7%" (one decimal only when it carries information). */
export function formatPercent(value: number | undefined | null, digits?: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  const percent = value * 100;
  if (digits != null) return `${percent.toFixed(digits)}%`;
  const rounded = Math.round(percent * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

export function signed(value: number): string {
  return `${value > 0 ? "+" : ""}${value}`;
}
