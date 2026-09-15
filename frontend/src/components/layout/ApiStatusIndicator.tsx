import { useApiStatus } from "@/hooks/useApiStatus";
import type { ApiConnectionStatus } from "@/types/api";

// "Live API" appears only after a successful health check; an unreachable backend is "API offline".
const META: Record<ApiConnectionStatus, { label: string; tone: "amber" | "cyan" | "green" | "red"; detail: string }> = {
  checking: { label: "Checking API", tone: "cyan", detail: "Contacting VayuDrishti API" },
  connected: { label: "Live API", tone: "green", detail: "Live API data" },
  syncing: { label: "Syncing", tone: "cyan", detail: "Refreshing live data" },
  disconnected: { label: "API offline", tone: "red", detail: "Unable to reach the API" },
};

/** Always-visible API connection pill in the top bar. */
export default function ApiStatusIndicator() {
  const api = useApiStatus();
  const meta = META[api.status];
  return (
    <div className={`api-status api-status-${meta.tone}`} title={meta.detail} data-testid="api-status" data-status={api.status}>
      <span className={`status-dot status-dot-${meta.tone}`} />
      <div className="api-status-copy">
        <strong data-testid="api-status-label">{meta.label}</strong>
      </div>
      {api.status === "disconnected" && <button type="button" className="api-status-action" onClick={api.recheck} data-testid="api-status-retry">Retry</button>}
    </div>
  );
}
