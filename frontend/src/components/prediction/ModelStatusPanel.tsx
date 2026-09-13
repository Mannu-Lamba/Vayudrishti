import { Boxes, Database, Server } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import type { ApiConnectionStatus, DataSource } from "@/types/api";
import type { ModelStatus, SystemComponentKind, SystemComponentStatus } from "@/types/model";

const STATUS_META: Record<ModelStatus, { label: string; tone: string }> = {
  ready: { label: "READY", tone: "green" },
  processing: { label: "PROCESSING", tone: "cyan" },
  unavailable: { label: "UNAVAILABLE", tone: "muted" },
  not_connected: { label: "NOT CONNECTED", tone: "muted" },
  error: { label: "ERROR", tone: "red" },
};

const KIND_ICON: Record<SystemComponentKind, typeof Boxes> = { model: Boxes, service: Server, dataset: Database };

/** The backend row always reflects the live connection check, not stored status. */
function backendRow(apiStatus: ApiConnectionStatus): Pick<SystemComponentStatus, "status" | "detail"> {
  switch (apiStatus) {
    case "demo": return { status: "not_connected", detail: "Demo mode · FastAPI data endpoints not queried" };
    case "checking": return { status: "processing", detail: "Checking connection" };
    case "disconnected": return { status: "error", detail: "Unable to reach the VayuDrishti API" };
    default: return { status: "ready", detail: "Reachable" };
  }
}

interface ModelStatusPanelProps {
  components: SystemComponentStatus[];
  apiStatus: ApiConnectionStatus;
  source?: DataSource;
  compact?: boolean;
}

export default function ModelStatusPanel({ components, apiStatus, source, compact = false }: ModelStatusPanelProps) {
  const rows = components.map((component) => (component.id === "backend-api" ? { ...component, ...backendRow(apiStatus) } : component));
  return (
    <Panel className={compact ? "model-status-compact" : ""} eyebrow="MODEL STATUS" title="Pipeline readiness" action={<DataSourceBadge source={source} />} data-testid="model-status-panel">
      <div className="model-status-list">
        {rows.map((row) => {
          const meta = STATUS_META[row.status];
          const Icon = KIND_ICON[row.kind];
          return (
            <div className="model-status-row" key={row.id} data-testid={`model-status-${row.id}`} data-status={row.status}>
              <Icon size={15} />
              <span className="model-status-copy"><strong>{row.label}</strong>{!compact && row.detail && <small>{row.detail}</small>}</span>
              <span className={`model-status-badge model-status-${meta.tone}`}><span className="model-status-dot" />{meta.label}</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
