import { BrainCircuit, Database, Gauge, MapPin, MapPinned, MoveUpRight, Wind } from "lucide-react";
import type { CycloneData } from "@/types/cyclone";
import Panel from "@/components/common/Panel";
import { formatMovement, formatObservedAt, orDash } from "@/lib/format";
import { formatCoordsCompact } from "@/lib/geo";

interface CycloneStatusProps {
  cyclone: CycloneData;
  /** Open the cyclone monitor focused on this system (/cyclones?cyclone=…). */
  onOpenMap?: () => void;
  onOpenPrediction?: () => void;
}

export default function CycloneStatus({ cyclone, onOpenMap, onOpenPrediction }: CycloneStatusProps) {
  const active = cyclone.status === "active";
  const tone = active ? "amber" : "muted";
  return <Panel className="cyclone-status-panel" eyebrow={`SELECTED STORM / ${cyclone.code}`} title={`${cyclone.name}${cyclone.season ? ` (${cyclone.season})` : ""}`} action={<span className={`status-badge status-badge-${tone}`}><span className={`status-dot status-dot-${tone}`} />{cyclone.status.toUpperCase()}</span>} data-testid="cyclone-status-panel">
    <div className="storm-identity"><div className="storm-code">{cyclone.basin}</div><div className="storm-category">{cyclone.category ?? "Category unknown"}</div><div className="storm-location"><MapPin size={13} />{cyclone.location.label} · {formatCoordsCompact(cyclone.location.latitude, cyclone.location.longitude)}</div></div>
    <div className="storm-primary-metrics">
      <div><Wind size={16} /><span className="metric-label">WIND</span><strong>{orDash(cyclone.windKmh)}<small> km/h</small></strong></div>
      <div><Gauge size={16} /><span className="metric-label">PRESSURE</span><strong>{orDash(cyclone.pressureHpa)}<small> hPa</small></strong></div>
      <div><MoveUpRight size={16} /><span className="metric-label">MOVEMENT</span><strong>{formatMovement(cyclone.movementDirection, cyclone.movementSpeedKmh)}</strong></div>
    </div>
    <div className="confidence-row"><div><div className="confidence-label"><span>Peak observed intensity</span><b>{cyclone.peakWindKmh != null ? `${cyclone.peakWindKmh} km/h` : "—"}</b></div><div className="confidence-note">{cyclone.peakCategory ?? "No wind recorded"}</div></div><div className="confidence-note"><Database size={14} />{cyclone.fixes ?? "—"} fixes · {cyclone.source ?? "cyclone_database"}</div></div>
    <div className="storm-footer">
      <div className="storm-footer-actions">
        {onOpenMap && <button type="button" className="text-action" onClick={onOpenMap} data-testid="cyclone-status-open-map"><MapPinned size={13} />View on map</button>}
        {onOpenPrediction && <button type="button" className="text-action" onClick={onOpenPrediction} data-testid="cyclone-status-open-prediction"><BrainCircuit size={13} />Open AI prediction</button>}
      </div>
      <span>Last observed {formatObservedAt(cyclone.observedAt)}</span>
    </div>
  </Panel>;
}
