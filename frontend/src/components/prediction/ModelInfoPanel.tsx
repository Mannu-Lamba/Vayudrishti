import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import type { DataSource } from "@/types/api";
import type { ModelInfo, ModelTask } from "@/types/model";

interface ModelInfoPanelProps {
  models: ModelInfo[];
  task?: ModelTask;
  /** Version reported by the prediction itself, when it differs from the registry. */
  predictionVersion?: string;
  source?: DataSource;
}

export default function ModelInfoPanel({ models, task = "track", predictionVersion, source }: ModelInfoPanelProps) {
  const primary = models.find((model) => model.task === task) ?? models[0];
  if (!primary) return null;
  const others = models.filter((model) => model.id !== primary.id);
  const rows: [string, string][] = [
    ["Model", primary.name],
    ["Version", predictionVersion ?? primary.version],
    ["Input window", primary.inputWindowHours ? `${primary.inputWindowHours} hours` : "—"],
    ["Forecast horizon", primary.forecastHorizonHours ? `${primary.forecastHorizonHours} hours` : "—"],
    ["Last updated", primary.lastUpdated ?? "—"],
    ["Inputs", primary.inputs?.join(" · ") ?? "—"],
  ];
  return (
    <Panel eyebrow="MODEL INFORMATION" title={primary.name} action={<DataSourceBadge source={source} />} data-testid="model-info-panel">
      <dl className="pred-facts pred-facts-tight">
        {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      {others.length > 0 && (
        <div className="model-info-others">
          {others.map((model) => <span key={model.id}><b>{model.name}</b>{model.version}</span>)}
        </div>
      )}
      {primary.notes && <div className="panel-note">{primary.notes}</div>}
    </Panel>
  );
}
