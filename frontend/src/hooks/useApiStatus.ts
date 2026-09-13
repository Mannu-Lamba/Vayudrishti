import { useIsFetching, useQuery } from "@tanstack/react-query";
import { environment } from "@/config/environment";
import { checkApiHealth } from "@/services/apiClient";
import { useDataMode } from "./useDataMode";
import { DATA_QUERY_ROOT } from "./useServiceQuery";
import type { ApiConnectionStatus } from "@/types/api";

/** Header/system status: DEMO MODE, CHECKING, API CONNECTED, SYNCING or API DISCONNECTED. */
export function useApiStatus() {
  const dataMode = useDataMode();
  const live = dataMode.mode === "live";
  const syncing = useIsFetching({ queryKey: [DATA_QUERY_ROOT, "live"] }) > 0;
  const health = useQuery({
    queryKey: ["api-health"],
    queryFn: checkApiHealth,
    enabled: live,
    refetchInterval: live ? environment.healthPollMs : false,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const status: ApiConnectionStatus = !live
    ? "demo"
    : health.isPending
      ? "checking"
      : !health.data?.reachable
        ? "disconnected"
        : syncing ? "syncing" : "connected";
  return { ...dataMode, status, lastCheckedAt: health.data?.checkedAt, recheck: () => { void health.refetch(); } };
}
