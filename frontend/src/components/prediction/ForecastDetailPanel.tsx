import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatPercent } from "@/lib/format";
import { formatLatitude, formatLongitude } from "@/lib/geo";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import { formatFrameTimestamp } from "@/lib/satellite";
import type { DataSource } from "@/types/api";
import type { ForecastPoint, PredictionAnchor } from "@/types/prediction";

interface ForecastDetailPanelProps {
  point: ForecastPoint | null;
  current: PredictionAnchor;
  source?: DataSource;
}

export default function ForecastDetailPanel({ point, current, source }: ForecastDetailPanelProps) {
  const { preferences } = usePreferences();
  const rows: [string, string, string][] = point
    ? [
      ["Valid time", formatFrameTimestamp(point.forecastTime), "time"],
      ["Latitude", formatLatitude(point.latitude), "lat"],
      ["Longitude", formatLongitude(point.longitude), "lon"],
      ["Wind", formatWind(point.windKmh, preferences.windUnit), "wind"],
      ...(point.windRangeKmh ? [["Wind range", `${formatWind(point.windRangeKmh[0], preferences.windUnit)} – ${formatWind(point.windRangeKmh[1], preferences.windUnit)}`, "wind-range"] as [string, string, string]] : []),
      ["Pressure", formatPressure(point.pressureHpa, preferences.pressureUnit), "pressure"],
      ...(point.category ? [["Category", point.category, "category"] as [string, string, string]] : []),
      ["Confidence", point.confidence == null ? "Not produced by the model" : formatPercent(point.confidence, 0), "confidence"],
      ["Uncertainty", point.uncertaintyRadiusKm ? `±${point.uncertaintyRadiusKm} km` : "Not provided", "uncertainty"],
    ]
    : [
      ["Observed", formatFrameTimestamp(current.observedAt), "time"],
      ["Latitude", formatLatitude(current.latitude), "lat"],
      ["Longitude", formatLongitude(current.longitude), "lon"],
      ["Wind", formatWind(current.windKmh, preferences.windUnit), "wind"],
      ["Pressure", formatPressure(current.pressureHpa, preferences.pressureUnit), "pressure"],
      ["Movement", current.movementDirection ? `${current.movementDirection} at ${current.movementSpeedKmh ?? "—"} km/h` : "—", "movement"],
    ];
  return (
    <Panel
      className="pred-detail-panel"
      eyebrow={point ? "SELECTED FORECAST POINT" : "SELECTED POINT"}
      title={point ? `Forecast — ${point.label.toUpperCase()}` : "Current observation"}
      action={<DataSourceBadge source={source} variant="model" />}
      data-testid="forecast-detail-panel"
    >
      <dl className="pred-facts pred-facts-tight">
        {rows.map(([label, value, key]) => <div key={key}><dt>{label}</dt><dd data-testid={`detail-${key}`}>{value}</dd></div>)}
      </dl>
    </Panel>
  );
}
