import { ExternalLink, Satellite, TimerReset } from "lucide-react";
import type { SatelliteFrame } from "@/types/satellite";
import type { DataSource } from "@/types/api";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import StateNotice from "@/components/common/StateNotice";
import InfraredPreview from "@/components/dashboard/InfraredPreview";

interface SatellitePreviewProps {
  frame: SatelliteFrame | null | undefined;
  source?: DataSource;
  onOpen: () => void;
}

export default function SatellitePreview({ frame, source, onOpen }: SatellitePreviewProps) {
  return <Panel className="satellite-preview-panel" eyebrow="SATELLITE INTELLIGENCE" title="Latest observation" action={<DataSourceBadge source={source} />} data-testid="satellite-preview-panel">
    {frame ? <>
      <InfraredPreview compact />
      <div className="satellite-meta-grid"><div><span className="metric-label">SOURCE</span><strong><Satellite size={14} />{frame.satellite}</strong></div><div><span className="metric-label">CHANNEL</span><strong>{frame.channel}</strong></div><div><span className="metric-label">CAPTURED</span><strong><TimerReset size={13} />{frame.capturedAt}</strong></div></div>
    </> : <div className="panel-body"><StateNotice variant="no-imagery" title="NO SATELLITE IMAGERY" message="No recent frame is available for this region." /></div>}
    <div className="panel-footer-link"><span>{frame ? `${frame.region} · ${frame.resolutionKm} km resolution` : "Satellite intelligence"}</span><button type="button" onClick={onOpen} data-testid="satellite-open-button"><ExternalLink size={13} />Open intelligence</button></div>
  </Panel>;
}
