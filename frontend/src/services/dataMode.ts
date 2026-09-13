// Which data the service layer serves: local demo data or the live FastAPI endpoints.
// Build-time default comes from VITE_USE_MOCK_DATA; operators can fall back to demo data at
// runtime when the API is unreachable ("Use demo data"), which lasts for the browser session.
import { environment } from "@/config/environment";
import type { Paginated, ServiceResult } from "@/types/api";

export type DataMode = "demo" | "live";

const OVERRIDE_KEY = "vayudrishti-data-mode";

/** What this build was configured for. */
export const configuredDataMode: DataMode = environment.useMockData ? "demo" : "live";

function readOverride(): DataMode | null {
  try {
    return sessionStorage.getItem(OVERRIDE_KEY) === "demo" ? "demo" : null;
  } catch {
    return null;
  }
}

let current: DataMode = configuredDataMode === "demo" ? "demo" : readOverride() ?? "live";
const listeners = new Set<() => void>();

export function getDataMode(): DataMode {
  return current;
}

export function isDemoMode(): boolean {
  return current === "demo";
}

export function setDataMode(next: DataMode): void {
  // A mock-data build has no API to switch to.
  if (next === "live" && configuredDataMode === "demo") return;
  if (next === current) return;
  current = next;
  try {
    if (next === "demo" && configuredDataMode === "live") sessionStorage.setItem(OVERRIDE_KEY, "demo");
    else sessionStorage.removeItem(OVERRIDE_KEY);
  } catch {
    // Storage can be blocked; the in-memory mode still applies.
  }
  listeners.forEach((listener) => listener());
}

export function subscribeDataMode(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Demo-side pagination so demo responses have the same shape as paged API responses. */
export function paginateDemo<T>(items: T[], page = 1, pageSize = 25): Paginated<T> {
  const safePage = Math.max(1, page);
  return { items: items.slice((safePage - 1) * pageSize, safePage * pageSize), page: safePage, pageSize, total: items.length };
}

/**
 * The single switch point between demo and live data. Every service function is
 * `serve({ demo, live })`; components never see which branch ran except via `source`.
 */
export async function serve<T>(handlers: { demo: () => T | Promise<T>; live: () => Promise<T>; demoLatencyMs?: number }): Promise<ServiceResult<T>> {
  if (isDemoMode()) {
    const data = await handlers.demo();
    if (handlers.demoLatencyMs) await wait(handlers.demoLatencyMs);
    return { data, source: "demo" };
  }
  return { data: await handlers.live(), source: "live" };
}
