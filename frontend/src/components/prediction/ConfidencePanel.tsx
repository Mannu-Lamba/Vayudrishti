import { Info } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatPercent } from "@/lib/format";
import type { DataSource } from "@/types/api";
import type { MlAssessment } from "@/types/model";
import type { PredictionConfidence } from "@/types/prediction";

interface ConfidencePanelProps {
  confidence: PredictionConfidence;
  /** Detection/classification from /ml/detect + /ml/classify when available. */
  assessment?: MlAssessment;
  source?: DataSource;
}

export default function ConfidencePanel({ confidence, assessment, source }: ConfidencePanelProps) {
  const classification = assessment?.classification;
  const detection = assessment?.detection;
  const bars: { id: string; label: string; value?: number; note?: string }[] = [
    { id: "track", label: "Track", value: confidence.track, note: "Predicted positions" },
    { id: "intensity", label: "Intensity", value: confidence.intensity, note: "Wind / pressure trend" },
    { id: "classification", label: "Classification", value: classification?.confidence ?? confidence.classification, note: classification?.category },
    { id: "detection", label: "Detection", value: detection?.confidence ?? confidence.detection, note: detection ? (detection.cycloneDetected ? "Cyclone signature detected" : "No cyclone detected") : undefined },
  ];
  return (
    <Panel eyebrow="MODEL CONFIDENCE" title="Confidence metrics" action={<DataSourceBadge source={source} variant="model" />} data-testid="confidence-panel">
      <div className="pred-confidence">
        {bars.map((bar) => (
          <div className="pred-confidence-row" key={bar.id} data-testid={`confidence-${bar.id}`}>
            <div className="pred-confidence-head"><span>{bar.label.toUpperCase()}</span><b>{formatPercent(bar.value)}</b></div>
            <div className="confidence-track"><span style={{ width: `${(bar.value ?? 0) * 100}%` }} /></div>
            {bar.note && <small>{bar.note}</small>}
          </div>
        ))}
      </div>
      {source === "demo" && <div className="panel-note"><Info size={14} />Demo values for interface design — not produced by a running model.</div>}
    </Panel>
  );
}
