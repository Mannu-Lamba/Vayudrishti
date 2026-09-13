// Central HTTP client for the FastAPI backend: base URL, JSON handling, timeouts and typed errors.
// Auth rides the httpOnly session cookie (credentials: "include") — never add auth headers here.
import { environment } from "@/config/environment";
import type { ApiHealth } from "@/types/api";

export type ApiErrorKind = "http" | "network" | "timeout" | "aborted" | "parse";

// Fields are declared, not constructor parameter properties: tsconfig sets
// erasableSyntaxOnly, which rejects `constructor(readonly status: number)`.
export class ApiError extends Error {
  /** HTTP status; 0 when no response arrived (network failure, timeout, abort). */
  status: number;
  body: unknown;
  kind: ApiErrorKind;

  constructor(status: number, body: unknown, kind: ApiErrorKind = "http") {
    super(kind === "http" ? `request failed with ${status}` : `request ${kind}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.kind = kind;
  }

  /** Worth retrying: connectivity trouble, rate limits and server-side failures. */
  get retryable(): boolean {
    return this.kind === "network" || this.kind === "timeout" || this.status === 429 || this.status >= 500;
  }

  /** The API could not be reached at all (as opposed to answering with an error). */
  get unreachable(): boolean {
    return this.kind === "network" || this.kind === "timeout" || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: QueryParams;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** `${VITE_API_BASE_URL}${path}?query` — empty query values are dropped. */
export function buildUrl(path: string, query?: QueryParams): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value != null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `${environment.apiBaseUrl}${cleanPath}${search ? `?${search}` : ""}`;
}

async function send(path: string, options: RequestOptions, accept: string): Promise<Response> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? environment.apiTimeoutMs;
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const forwardAbort = () => controller.abort();
  options.signal?.addEventListener("abort", forwardAbort, { once: true });
  const hasBody = options.body !== undefined;
  // FormData (file uploads) sets its own multipart boundary header; everything else is JSON.
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  try {
    const response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      credentials: "include",
      headers: { Accept: accept, ...(hasBody && !isForm ? { "Content-Type": "application/json" } : {}) },
      body: hasBody ? (isForm ? (options.body as FormData) : JSON.stringify(options.body)) : undefined,
      signal: controller.signal,
    });
    // FastAPI reports request-validation failures as 422 with a {detail: [...]} body.
    if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null));
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) throw new ApiError(0, null, "timeout");
    if (options.signal?.aborted) throw new ApiError(0, null, "aborted");
    throw new ApiError(0, null, "network");
  } finally {
    // Cleared once headers arrive, so long-running streams are not cut off.
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options, "application/json");
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, null, "parse");
  }
}

// The response type is yours to declare: nothing infers across the Python boundary, so a
// TS interface here mirrors the endpoint's Pydantic model by hand — keep the two in sync.
export const apiGet = <T>(path: string, query?: QueryParams, signal?: AbortSignal) => apiRequest<T>(path, { query, signal });
export const apiPost = <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body: body ?? null });
export const apiPut = <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body: body ?? null });
export const apiPatch = <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body: body ?? null });
export const apiDelete = <T>(path: string) => apiRequest<T>(path, { method: "DELETE" });

export async function apiStream(path: string, body: unknown): Promise<ReadableStream<Uint8Array>> {
  const response = await send(path, { method: "POST", body }, "text/event-stream");
  if (!response.body) throw new Error("stream response has no body");
  return response.body;
}

/** A 404 from a resource endpoint means "nothing available yet", not a failure. */
export async function orNullOn404<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export interface ApiReachability {
  reachable: boolean;
  checkedAt: string;
  health?: ApiHealth;
}

/**
 * Probe GET /health. Any 2xx–4xx reply proves the backend is up (the route may not exist yet);
 * network failures, timeouts and 5xx (incl. a dev-proxy with no backend behind it) mean it is not.
 */
export async function checkApiHealth(): Promise<ApiReachability> {
  const checkedAt = new Date().toISOString();
  try {
    const health = await apiRequest<ApiHealth>("/health", { timeoutMs: 5_000 });
    return { reachable: true, checkedAt, health };
  } catch (error) {
    const answered = error instanceof ApiError && error.kind === "http" && error.status < 500;
    return { reachable: answered, checkedAt };
  }
}

export interface ApiErrorCopy {
  title: string;
  message: string;
}

/** Operator-facing wording for any failure — never raw bodies, stack traces or URLs. */
export function describeApiError(error: unknown): ApiErrorCopy {
  if (!(error instanceof ApiError)) return { title: "UNEXPECTED ERROR", message: "Something went wrong while loading this data." };
  if (error.kind === "timeout") return { title: "REQUEST TIMED OUT", message: "The VayuDrishti API took too long to respond." };
  if (error.kind === "network") return { title: "BACKEND UNAVAILABLE", message: "Unable to connect to the VayuDrishti API." };
  if (error.kind === "parse") return { title: "UNEXPECTED RESPONSE", message: "The API returned data this console could not read." };
  if (error.kind === "aborted") return { title: "REQUEST CANCELLED", message: "The request was cancelled before it finished." };
  switch (error.status) {
    case 400: return { title: "INVALID REQUEST", message: "The API could not process this request." };
    case 401: return { title: "SESSION EXPIRED", message: "Sign in again to continue." };
    case 403: return { title: "ACCESS DENIED", message: "Your operator role cannot access this data." };
    case 404: return { title: "NOT AVAILABLE", message: "The API does not provide this data yet." };
    case 422: return { title: "INVALID PARAMETERS", message: "The API rejected the selected filters." };
    case 429: return { title: "RATE LIMITED", message: "Too many requests — wait a moment and retry." };
    case 502:
    case 503:
    case 504: return { title: "SERVICE UNAVAILABLE", message: "The API or inference service is temporarily unavailable." };
    default:
      return error.status >= 500
        ? { title: "SERVER ERROR", message: "The API hit an internal error. Try again shortly." }
        : { title: "REQUEST FAILED", message: "The API could not complete this request." };
  }
}
