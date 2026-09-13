// Cross-cutting API contracts shared by every service.

/** Where a value came from — shown next to every data/AI visualization. */
export type DataSource = "demo" | "live" | "historical";

/** Every service call returns its payload together with its provenance. */
export interface ServiceResult<T> {
  data: T;
  source: DataSource;
}

export type ApiConnectionStatus = "demo" | "checking" | "connected" | "disconnected" | "syncing";

/** Future list endpoints page their results instead of shipping whole datasets to the browser. */
export interface PageQuery {
  page?: number;
  pageSize?: number;
}

/** ISO 8601 bounds, e.g. GET /api/cyclones/{id}/track?start=…&end=… */
export interface DateRangeQuery {
  start?: string;
  end?: string;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

/** GET /api/health — optional; any HTTP reply already proves the API is reachable. */
export interface ApiHealth {
  status?: "ok" | "degraded";
  version?: string;
  timestamp?: string;
  /** Which deployed models are genuinely loaded (backend/routers/health.py). */
  services?: { api: boolean; identification_model: boolean; classification_model: boolean; prediction_model: boolean };
}
