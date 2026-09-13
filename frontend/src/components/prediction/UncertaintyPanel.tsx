import { Info } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import type { DataSource } from "@/types/api";
import type { CyclonePrediction } from "@/types/prediction";

interface UncertaintyPanelProps {
  prediction: CyclonePrediction;
  selectedHours: number;
  onSelect: (hours: number) => void;
  source?: DataSource;
}

/** Explains what the corridor on the map is — and, in demo mode, what it is not. */
export default function UncertaintyPanel({ prediction, selectedHours, onSelect, source }: UncertaintyPanelProps) {
  const uncertainty = prediction.uncertainty;
  const note = uncertainty?.polygon?.length
    ? "Prediction polygon supplied by the forecast service."
    : uncertainty?.method === "demo"
      ? uncertainty.note ?? "Illustrative radii only — not a scientifically calculated probability cone."
      : uncertainty?.method === "empirical"
        ? uncertainty.note ?? "Empirical radius from the model's validation errors — not a per-forecast probability."
      : prediction.forecast.some((point) => point.uncertaintyRadiusKm)
        ? `Radii supplied by the forecast service${uncertainty?.confidenceLevel ? ` (${Math.round(uncertainty.confidenceLevel * 100)}% level)` : ""}.`
        : "No uncertainty supplied — the corridor shows a nominal width.";
  return (
    <Panel eyebrow="PREDICTION UNCERTAINTY" title={uncertainty?.method === "demo" ? "Demo uncertainty corridor" : uncertainty?.method === "empirical" ? `Uncertainty radius (${Math.round((uncertainty.confidenceLevel ?? 0) * 100)}% of past errors)` : "Uncertainty corridor"} action={<DataSourceBadge source={source} variant="model" />} data-testid="uncertainty-panel">
      <div className="pred-uncertainty-list">
        {prediction.forecast.map((point) => (
          <button
            type="button"
            key={point.id}
            className={`pred-uncertainty-item ${point.hours === selectedHours ? "pred-uncertainty-active" : ""}`}
            aria-pressed={point.hours === selectedHours}
            onClick={() => onSelect(point.hours)}
            data-testid={`uncertainty-${point.hours}`}
          >
            <small>{point.label.toUpperCase()}</small>
            <strong>{point.uncertaintyRadiusKm ? `±${point.uncertaintyRadiusKm} km` : "—"}</strong>
          </button>
        ))}
      </div>
      <div className="panel-note"><Info size={14} />{note}</div>
    </Panel>
  );
}
