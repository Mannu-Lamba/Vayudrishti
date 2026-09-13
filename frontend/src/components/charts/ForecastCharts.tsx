import { useId, useMemo } from "react";
import { Area, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import LoadingBlock from "@/components/common/LoadingBlock";
import StateNotice from "@/components/common/StateNotice";
import type { DataSource } from "@/types/api";
import type { CyclonePrediction } from "@/types/prediction";

// Chart config hoisted out of render: stable references keep Recharts from re-diffing every paint.
const CHART_MARGIN = { top: 12, right: 12, left: -12, bottom: 0 };
const WIND_COLOR = "#7ab4f0";
const PRESSURE_COLOR = "#f59e0b";
const GRID_COLOR = "#2a2f36";
const AXIS_TICK = { fill: "#6f7782", fontSize: 11 };
const WIND_DOT = { fill: "#15181c", stroke: WIND_COLOR, strokeWidth: 2, r: 3 };
const PRESSURE_DOT = { fill: "#15181c", stroke: PRESSURE_COLOR, strokeWidth: 2, r: 3 };
const ACTIVE_DOT = { r: 5 };

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value?: number; dataKey?: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><div className="chart-tooltip-time">{label}</div>{payload.filter((entry) => entry.dataKey === "wind" || entry.dataKey === "pressure").slice(0, 1).map((entry) => <div className="chart-tooltip-row" key={entry.dataKey}><span>{entry.dataKey === "wind" ? "Wind" : "Pressure"}</span><b>{entry.value} {entry.dataKey === "wind" ? "km/h" : "hPa"}</b></div>)}</div>;
}

function paddedDomain(values: number[], pad: number, step: number): [number, number] {
  if (!values.length) return [0, 1];
  return [Math.floor((Math.min(...values) - pad) / step) * step, Math.ceil((Math.max(...values) + pad) / step) * step];
}

interface ForecastChartsProps {
  prediction?: CyclonePrediction | null;
  source?: DataSource;
  loading?: boolean;
  expanded?: boolean;
  /** Highlighted horizon in hours (0 = now). */
  selectedHours?: number | null;
}

/** Intensity (wind) and pressure forecasts from the observed state through every horizon. */
export default function ForecastCharts({ prediction, source, loading = false, expanded = false, selectedHours }: ForecastChartsProps) {
  const chartId = useId();
  const series = useMemo(() => (prediction
    ? [
      { label: "NOW", hours: 0, wind: prediction.current.windKmh, pressure: prediction.current.pressureHpa },
      ...prediction.forecast.map((point) => ({ label: point.label.toUpperCase(), hours: point.hours, wind: point.windKmh, pressure: point.pressureHpa })),
    ]
    : []), [prediction]);
  const windDomain = useMemo(() => paddedDomain(series.map((point) => point.wind), 8, 10), [series]);
  const pressureDomain = useMemo(() => paddedDomain(series.map((point) => point.pressure), 4, 5), [series]);
  const selectedLabel = series.find((point) => point.hours === selectedHours)?.label;

  const body = (kind: "wind" | "pressure") => {
    if (loading) return <div className="panel-body"><LoadingBlock label="LOADING FORECAST" rows={4} /></div>;
    if (!series.length) return <div className="panel-body"><StateNotice variant="empty" title="NO FORECAST AVAILABLE" message="There is no forecast for the selected cyclone." /></div>;
    const wind = kind === "wind";
    return (
      <>
        <div className="chart-legend"><span><i className={`legend-line ${wind ? "legend-line-cyan" : "legend-line-amber"}`} />{wind ? "Wind speed" : "Central pressure"}</span><span className="chart-units">{wind ? "km/h" : "hPa"}</span></div>
        <div className="chart-wrap" data-testid={wind ? "wind-speed-chart" : "pressure-trend-chart"}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={CHART_MARGIN}>
              {wind && <defs><linearGradient id={`${chartId}-wind-fill`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={WIND_COLOR} stopOpacity=".2" /><stop offset="1" stopColor={WIND_COLOR} stopOpacity="0" /></linearGradient></defs>}
              <CartesianGrid stroke={GRID_COLOR} strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <YAxis domain={wind ? windDomain : pressureDomain} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip />} />
              {selectedLabel && <ReferenceLine x={selectedLabel} stroke={PRESSURE_COLOR} strokeDasharray="3 3" strokeOpacity={0.8} />}
              {wind && <Area type="monotone" dataKey="wind" stroke="none" fill={`url(#${chartId}-wind-fill)`} />}
              <Line type="monotone" dataKey={kind} stroke={wind ? WIND_COLOR : PRESSURE_COLOR} strokeWidth={2} dot={wind ? WIND_DOT : PRESSURE_DOT} activeDot={ACTIVE_DOT} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </>
    );
  };

  return (
    <div className={`charts-grid ${expanded ? "charts-grid-expanded" : ""}`} data-testid="forecast-charts">
      <Panel eyebrow="MODEL OUTPUT / INTENSITY" title="Intensity forecast" action={<DataSourceBadge source={source} variant="model" />} data-testid="wind-chart-panel">{body("wind")}</Panel>
      <Panel eyebrow="MODEL OUTPUT / PRESSURE" title="Pressure forecast" action={<DataSourceBadge source={source} variant="model" />} data-testid="pressure-chart-panel">{body("pressure")}</Panel>
    </div>
  );
}
