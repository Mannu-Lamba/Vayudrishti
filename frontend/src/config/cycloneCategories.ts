import type { ExpressionSpecification } from "maplibre-gl";

/**
 * Marker colour for the category the API returns. The colours are the design guideline's
 * `cyclone_categories` palette for the IMD scale. Categories from other warning centres take the
 * colour of the IMD category with the same published wind band (JMA/NHC "Tropical Storm" and
 * Météo-France "Moderate Tropical Storm" are 34–47 kt like IMD "Cyclonic Storm"; "Severe Tropical
 * Storm" is 48–63 kt like "Severe Cyclonic Storm"). "Typhoon" and "Hurricane" start at 64 kt, so
 * without a finer label from the API they take the "Very Severe Cyclonic Storm" colour.
 * The mapping depends only on the label: the frontend never derives a category from wind speed.
 */
const IMD_COLORS = {
  depression: "#3b82f6",
  deepDepression: "#06b6d4",
  cyclonicStorm: "#10b981",
  severe: "#f59e0b",
  verySevere: "#f97316",
  extremelySevere: "#ef4444",
  superCyclonic: "#dc2626",
};

export const CATEGORY_COLORS: Record<string, string> = {
  Depression: IMD_COLORS.depression,
  "Tropical Depression": IMD_COLORS.depression,
  "Deep Depression": IMD_COLORS.deepDepression,
  "Cyclonic Storm": IMD_COLORS.cyclonicStorm,
  "Moderate Tropical Storm": IMD_COLORS.cyclonicStorm,
  "Tropical Storm": IMD_COLORS.cyclonicStorm,
  "Severe Cyclonic Storm": IMD_COLORS.severe,
  "Severe Tropical Storm": IMD_COLORS.severe,
  "Very Severe Cyclonic Storm": IMD_COLORS.verySevere,
  Typhoon: IMD_COLORS.verySevere,
  Hurricane: IMD_COLORS.verySevere,
  "Extremely Severe Cyclonic Storm": IMD_COLORS.extremelySevere,
  "Super Cyclonic Storm": IMD_COLORS.superCyclonic,
};

/** Categories the table does not know (new labels from the API) are drawn neutral, not guessed. */
export const UNKNOWN_CATEGORY_COLOR = "#9aa2ad";

export function categoryColor(category: string | undefined): string {
  return (category && CATEGORY_COLORS[category]) || UNKNOWN_CATEGORY_COLOR;
}

/** Same table as a MapLibre paint expression over a feature's `category` property. */
export const categoryColorExpression = [
  "match",
  ["get", "category"],
  ...Object.entries(CATEGORY_COLORS).flat(),
  UNKNOWN_CATEGORY_COLOR,
] as unknown as ExpressionSpecification;
