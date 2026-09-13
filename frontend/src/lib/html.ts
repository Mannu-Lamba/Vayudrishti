const ENTITIES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" };

/** Escape text for MapLibre popups built with setHTML — strings from the API must never become markup. */
export function escapeHtml(value: unknown): string {
  return String(value).replace(/[&<>"']/g, (character) => ENTITIES[character]);
}
