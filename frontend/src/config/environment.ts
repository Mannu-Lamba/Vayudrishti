// Public runtime configuration. Everything here is compiled into the browser bundle, so only
// non-secret values may come from VITE_* variables (see frontend/.env.example).

export type PredictionStrategy = "resource" | "inference";

const env = import.meta.env;

function positiveNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const environment = {
  /** FastAPI base URL. Relative by default so the httpOnly session cookie stays same-origin. */
  apiBaseUrl: (env.VITE_API_BASE_URL?.trim() || "/api").replace(/\/+$/, ""),
  /** Per-request timeout for JSON calls (streams only time out until headers arrive). */
  apiTimeoutMs: positiveNumber(env.VITE_API_TIMEOUT_MS, 15_000),
  /** How predictions are obtained in live mode: stored resource vs on-demand inference. */
  predictionStrategy: (env.VITE_PREDICTION_STRATEGY === "inference" ? "inference" : "resource") as PredictionStrategy,
  /** How often the header re-checks API reachability in live mode. */
  healthPollMs: 30_000,
} as const;
