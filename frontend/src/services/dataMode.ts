// The console reads the live FastAPI endpoints only: there is no demo data mode and no demo fallback.
// `serve` stays the single exit of every service, so each result still carries its provenance.
import type { ServiceResult } from "@/types/api";

export type DataMode = "live";

export const configuredDataMode: DataMode = "live";

export function getDataMode(): DataMode {
  return "live";
}

export async function serve<T>(handlers: { live: () => Promise<T> }): Promise<ServiceResult<T>> {
  return { data: await handlers.live(), source: "live" };
}
