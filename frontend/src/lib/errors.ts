import { ApiError } from "@/services/apiClient";

/** Extracts a human-readable message from an ApiError, falling back to a default. */
export function errorDetail(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg).replace(/^Value error, /, "");
  }
  return fallback;
}
