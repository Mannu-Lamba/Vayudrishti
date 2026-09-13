import type { KeyboardEvent } from "react";
import Panel from "@/components/common/Panel";
import { formatPercent } from "@/lib/format";
import type { ForecastPoint, PredictionAnchor } from "@/types/prediction";

interface PredictionTimelineProps {
  current: PredictionAnchor;
  /** Any number of horizons — 6–24 h today, 36 / 48 / 72 h later without changes here. */
  forecast: ForecastPoint[];
  /** 0 = current observation. */
  selectedHours: number;
  onSelect: (hours: number) => void;
}

export default function PredictionTimeline({ current, forecast, selectedHours, onSelect }: PredictionTimelineProps) {
  const steps = [
    { hours: 0, label: "CURRENT", windKmh: current.windKmh, confidence: undefined as number | undefined },
    ...forecast.map((point) => ({ hours: point.hours, label: point.label.toUpperCase(), windKmh: point.windKmh, confidence: point.confidence })),
  ];
  const index = Math.max(0, steps.findIndex((step) => step.hours === selectedHours));
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = event.key === "ArrowRight" ? index + 1 : event.key === "ArrowLeft" ? index - 1 : event.key === "Home" ? 0 : event.key === "End" ? steps.length - 1 : null;
    if (next == null || !steps[next]) return;
    event.preventDefault();
    onSelect(steps[next].hours);
  };
  return (
    <Panel className="pred-timeline-panel" data-testid="prediction-timeline">
      <div className="pred-timeline" onKeyDown={onKeyDown}>
        <span className="sat-control-label pred-timeline-heading">FORECAST HORIZON</span>
        <div className="pred-steps" role="group" aria-label="Forecast horizon" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(96px, 1fr))` }}>
          {steps.map((step) => {
            const active = step.hours === selectedHours;
            return (
              <button
                type="button"
                key={step.hours}
                className={`pred-step ${active ? "pred-step-active" : ""} ${step.hours === 0 ? "pred-step-current" : ""}`}
                aria-pressed={active}
                onClick={() => onSelect(step.hours)}
                data-testid={`prediction-step-${step.hours}`}
              >
                <span className="pred-step-dot" />
                <strong>{step.label}</strong>
                <span>{step.windKmh} km/h</span>
                {step.hours === 0
                  ? <span className="pred-step-confidence pred-step-observed"><small>OBSERVED</small></span>
                  : step.confidence != null
                    ? <span className="pred-step-confidence"><i style={{ width: `${step.confidence * 100}%` }} /><small>{formatPercent(step.confidence, 0)}</small></span>
                    : <span className="pred-step-confidence pred-step-observed"><small>FORECAST</small></span>}
              </button>
            );
          })}
        </div>
      </div>
    </Panel>
  );
}
