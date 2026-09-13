const UTC_FORMAT = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatUtc(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : `${UTC_FORMAT.format(date).replace(",", "")} UTC`;
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) return "—";
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** ISO 8601 from an ISO string or a display timestamp such as "08 Sep 2026 · 14:30 UTC". Unparseable input is returned unchanged. */
export function toIsoTimestamp(value: string): string {
  if (!Number.isNaN(Date.parse(value))) return new Date(value).toISOString();
  const match = /(\d{1,2}) (\w{3}) (\d{4})\D+(\d{2}):(\d{2})/.exec(value);
  if (!match) return value;
  const month = MONTHS.indexOf(match[2]);
  return new Date(Date.UTC(Number(match[3]), month, Number(match[1]), Number(match[4]), Number(match[5]))).toISOString();
}
