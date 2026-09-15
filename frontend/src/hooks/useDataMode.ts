import { configuredDataMode, getDataMode } from "@/services/dataMode";

/** Data mode for query keys and provenance badges. Always the live API — the console has no demo mode. */
export function useDataMode() {
  const mode = getDataMode();
  return { mode, configuredMode: configuredDataMode, isDemo: false as const };
}
