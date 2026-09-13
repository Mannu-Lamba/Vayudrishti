import { useSyncExternalStore } from "react";
import { configuredDataMode, getDataMode, setDataMode, subscribeDataMode } from "@/services/dataMode";

/** Current data mode plus the runtime switch used by "Use demo data" / "Retry live API". */
export function useDataMode() {
  const mode = useSyncExternalStore(subscribeDataMode, getDataMode, getDataMode);
  return {
    mode,
    configuredMode: configuredDataMode,
    isDemo: mode === "demo",
    /** Demo data shown although this build is configured for the live API. */
    isFallback: mode === "demo" && configuredDataMode === "live",
    switchToDemo: () => setDataMode("demo"),
    switchToLive: () => setDataMode("live"),
  };
}
