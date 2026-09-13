import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ApiError } from "@/services/apiClient";
import { useDataMode } from "./useDataMode";
import type { DataSource, ServiceResult } from "@/types/api";

/** Root of every data query key: [DATA_QUERY_ROOT, mode, ...key] — switching mode refetches. */
export const DATA_QUERY_ROOT = "vd-data";

export interface ServiceQueryState<T> {
  data: T | undefined;
  source: DataSource | undefined;
  /** First load, nothing to show yet. */
  loading: boolean;
  /** Any request in flight, including refreshes. */
  fetching: boolean;
  error: unknown;
  /** Showing the previous key's data while the new one loads. */
  stale: boolean;
  refetch: () => void;
}

interface ServiceQueryOptions {
  enabled?: boolean;
  keepPrevious?: boolean;
  /** Re-fetch on this interval while mounted (status badges). */
  refetchIntervalMs?: number;
}

export function dataQueryOptions(mode: string) {
  return {
    // Demo data never changes; live data refreshes when stale or on demand.
    staleTime: mode === "demo" ? Infinity : 60_000,
    // Retry only transient failures (network, timeout, 429, 5xx), and only against the API.
    retry: (failureCount: number, error: unknown) => mode === "live" && failureCount < 2 && error instanceof ApiError && error.retryable,
    refetchOnWindowFocus: false,
  };
}

/** Shared React Query wrapper behind every data hook: loading / data / error / refetch + provenance. */
export function useServiceQuery<T>(key: readonly unknown[], fetcher: () => Promise<ServiceResult<T>>, options: ServiceQueryOptions = {}): ServiceQueryState<T> {
  const { mode } = useDataMode();
  const query = useQuery({
    queryKey: [DATA_QUERY_ROOT, mode, ...key],
    queryFn: fetcher,
    enabled: options.enabled ?? true,
    placeholderData: options.keepPrevious ? keepPreviousData : undefined,
    refetchInterval: options.refetchIntervalMs ?? false,
    ...dataQueryOptions(mode),
  });
  return {
    data: query.data?.data,
    source: query.data?.source,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    stale: query.isPlaceholderData,
    refetch: () => { void query.refetch(); },
  };
}
