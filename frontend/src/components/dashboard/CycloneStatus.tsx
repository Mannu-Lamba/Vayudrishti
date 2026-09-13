import { BrainCircuit, Crosshair, Gauge, MapPin, MapPinned, MoveUpRight, Wind } from "lucide-react";
import type { CycloneData } from "@/types/cyclone";
import Panel from "@/components/common/Panel";
import { formatCoordsCompact } from "@/lib/geo";

interface CycloneStatusProps {
  cyclone: CycloneData;
  /** Open the cyclone monitor focused on this system (/cyclones?cyclone=…). */
  onOpenMap?: () => void;
  onOpenPrediction?: () => void;
}

export default function CycloneStatus({ cyclone, onOpenMap, onOpenPrediction }: CycloneStatusProps) {
  return <Panel className="cyclone-status-panel" eyebrow={`PRIMARY SYSTEM / ${cyclone.code}`} title={`Cyclone ${cyclone.name}`} action={<span className="status-badge status-badge-amber"><span className="status-dot status-dot-amber" />{cyclone.status.toUpperCase()}</span>} data-testid="cyclone-status-panel">
    <div className="storm-identity"><div className="storm-code">{cyclone.code}</div><div className="storm-category">{cyclone.category}</div><div className="storm-location"><MapPin size={13} />{cyclone.location.label} · {formatCoordsCompact(cyclone.location.latitude, cyclone.location.longitude)}</div></div>
    <div className="storm-primary-metrics">
      <div><Wind size={16} /><span className="metric-label">WIND</span><strong>{cyclone.windKmh}<small> km/h</small></strong></div>
      <div><Gauge size={16} /><span className="metric-label">PRESSURE</span><strong>{cyclone.pressureHpa}<small> hPa</small></strong></div>
      <div><MoveUpRight size={16} /><span className="metric-label">MOVEMENT</span><strong>{cyclone.movementDirection}<small> / {cyclone.movementSpeedKmh} km/h</small></strong></div>
    </div>
    <div className="confidence-row"><div><div className="confidence-label"><span>AI detection confidence</span><b>{cyclone.detectionConfidence}%</b></div><div className="confidence-track"><span style={{ width: `${cyclone.detectionConfidence}%` }} /></div></div><div className="confidence-note"><Crosshair size={14} />T-NUMBER {cyclone.dvorakTNumber}</div></div>
    <div className="storm-footer">
      <div className="storm-footer-actions">
        {onOpenMap && <button type="button" className="text-action" onClick={onOpenMap} data-testid="cyclone-status-open-map"><MapPinned size={13} />View on map</button>}
        {onOpenPrediction && <button type="button" className="text-action" onClick={onOpenPrediction} data-testid="cyclone-status-open-prediction"><BrainCircuit size={13} />Open AI prediction</button>}
      </div>
      <span>{cyclone.observedAt}</span>
    </div>
  </Panel>;
}
