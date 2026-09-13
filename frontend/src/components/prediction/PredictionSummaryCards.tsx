import { Gauge, Radar, Route, Tags, Wind } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatPercent, signed } from "@/lib/format";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import type { DataSource } from "@/types/api";
import type { CyclonePrediction, ForecastPoint } from "@/types/prediction";

interface PredictionSummaryCardsProps {
  prediction: CyclonePrediction;
  /** Selected horizon; null = the current observation. */
  selected: ForecastPoint | null;
  source?: DataSource;
  classificationConfidence?: number;
}

interface Card {
  id: string;
  label: string;
  value: string;
  context: string;
  icon: LucideIcon;
  tone: "cyan" | "amber";
}

export default function PredictionSummaryCards({ prediction, selected, source, classificationConfidence }: PredictionSummaryCardsProps) {
  const { preferences } = usePreferences();
  const current = prediction.current;
  const at = selected ? `At ${selected.label.toUpperCase()}` : "Observed now";
  const cards: Card[] = [
    {
      id: "wind", label: selected ? "Predicted wind" : "Current wind", icon: Wind, tone: "amber",
      value: formatWind(selected?.windKmh ?? current.windKmh, preferences.windUnit),
      context: selected ? `${at} · ${signed(selected.windKmh - current.windKmh)} km/h vs now` : at,
    },
    {
      id: "pressure", label: selected ? "Predicted pressure" : "Current pressure", icon: Gauge, tone: "amber",
      value: formatPressure(selected?.pressureHpa ?? current.pressureHpa, preferences.pressureUnit),
      context: selected ? `${at} · ${signed(selected.pressureHpa - current.pressureHpa)} hPa vs now` : at,
    },
    { id: "track", label: "Track confidence", icon: Route, tone: "cyan", value: formatPercent(prediction.confidence.track), context: "Position forecast" },
    { id: "intensity", label: "Intensity confidence", icon: Radar, tone: "cyan", value: formatPercent(prediction.confidence.intensity), context: "Wind / pressure forecast" },
    { id: "classification", label: "Classification confidence", icon: Tags, tone: "cyan", value: formatPercent(classificationConfidence ?? prediction.confidence.classification), context: String(current.category) },
  ];
  return (
    <Panel eyebrow="AI PREDICTION SUMMARY" title={selected ? `Outlook at ${selected.label.toUpperCase()}` : "Current observation"} action={<DataSourceBadge source={source} variant="model" />} data-testid="prediction-summary-cards">
      <div className="pred-cards">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div className={`pred-card pred-card-${card.tone}`} key={card.id} data-testid={`pred-card-${card.id}`}>
              <span className="pred-card-top"><span className="metric-label">{card.label}</span><Icon size={14} /></span>
              <strong data-testid={`pred-card-${card.id}-value`}>{card.value}</strong>
              <small>{card.context}</small>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
