import { useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";

export type SearchPatch = Record<string, string | null | undefined>;

/**
 * URL query params as page state: selections survive reloads, are shareable, and carry across
 * pages (satellite ⇄ cyclone map). Updates replace the history entry so switching regions does
 * not flood the back button.
 */
export function useSearchParamState() {
  const [params, setParams] = useSearchParams();
  // React Router's functional updater reads the params of the last *render*, so two updates
  // before a re-render (e.g. channel then source) would drop the first. Patch a ref instead.
  const latest = useRef(params);
  latest.current = params;
  const update = useCallback((patch: SearchPatch) => {
    const next = new URLSearchParams(latest.current);
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    }
    latest.current = next;
    setParams(next, { replace: true });
  }, [setParams]);
  return [params, update] as const;
}

/** "?region=…&subregion=…" with empty values dropped. */
export function buildSearch(patch: SearchPatch) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(patch)) {
    if (value != null && value !== "") params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}
