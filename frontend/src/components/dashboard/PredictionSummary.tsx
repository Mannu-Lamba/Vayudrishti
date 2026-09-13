import type { CSSProperties } from "react";
import { ArrowRight, ChevronRight } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import ApiErrorState from "@/components/common/ApiErrorState";
import LoadingBlock from "@/components/common/LoadingBlock";
import StateNotice from "@/components/common/StateNotice";
import { formatPercent } from "@/lib/format";
import type { DataSource } from "@/types/api";
import type { CyclonePrediction } from "@/types/prediction";

interface PredictionSummaryProps {
  prediction: CyclonePrediction | null | undefined;
  source?: DataSource;
  loading: boolean;
  error?: unknown;
  onRetry?: () => void;
  onOpen: () => void;
}

/** Dashboard outlook card: observed → each forecast horizon, plus headline confidences. */
export default function PredictionSummary({ prediction, source, loading, error, onRetry, onOpen }: PredictionSummaryProps) {
  const points = prediction
    ? [{ key: "now", horizon: "CURRENT", windKmh: prediction.current.windKmh, pressureHpa: prediction.current.pressureHpa }, ...prediction.forecast.map((point) => ({ key: point.id, horizon: point.label.toUpperCase(), windKmh: point.windKmh, pressureHpa: point.pressureHpa }))]
    : [];
  return <Panel className="prediction-summary-panel" eyebrow="FORECAST SIGNAL" title="Intensity outlook" action={<DataSourceBadge source={source} variant="model" />} data-testid="prediction-summary-panel">
    {loading ? <div className="panel-body"><LoadingBlock label="LOADING PREDICTION" /></div>
      : error ? <div className="panel-body"><ApiErrorState error={error} onRetry={onRetry} subject="the prediction" /></div>
        : !prediction ? <div className="panel-body"><StateNotice variant="empty" title="NO PREDICTION AVAILABLE" message="The selected cyclone does not currently have a prediction result." /></div>
          : <>
            <div className="forecast-row" style={{ "--forecast-cols": points.length } as CSSProperties}>{points.map((point, index) => <div className={`forecast-point ${index === 0 ? "forecast-point-current" : ""}`} key={point.key} data-testid={`forecast-point-${index}`}><span className="forecast-horizon">{point.horizon}</span><strong>{point.windKmh}<small>km/h</small></strong><span className="forecast-pressure">{point.pressureHpa} hPa</span>{index < points.length - 1 && <ArrowRight className="forecast-arrow" size={14} />}</div>)}</div>
            <div className="confidence-grid">{([["Track confidence", prediction.confidence.track], ["Intensity confidence", prediction.confidence.intensity], ["Classification confidence", prediction.confidence.classification]] as const).map(([label, value]) => <div className="mini-confidence" key={label}><div><span>{label}</span><b>{formatPercent(value)}</b></div><div className="confidence-track"><span style={{ width: `${(value ?? 0) * 100}%` }} /></div></div>)}</div>
          </>}
    <button type="button" className="text-action" onClick={onOpen} data-testid="prediction-open-button">View full prediction workspace <ChevronRight size={14} /></button>
  </Panel>;
}
