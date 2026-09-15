import { ExternalLink, ImageOff, Satellite, TimerReset } from "lucide-react";
import type { SatelliteFrame } from "@/types/satellite";
import type { DataSource } from "@/types/api";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import StateNotice from "@/components/common/StateNotice";
import { formatObservedAt } from "@/lib/format";

interface SatellitePreviewProps {
  frame: SatelliteFrame | null | undefined;
  source?: DataSource;
  onOpen: () => void;
}

/** The latest satellite frame record of the region. No picture is drawn unless the database stores the image. */
export default function SatellitePreview({ frame, source, onOpen }: SatellitePreviewProps) {
  return <Panel className="satellite-preview-panel" eyebrow="SATELLITE INTELLIGENCE" title="Latest frame record" action={<DataSourceBadge source={source} />} data-testid="satellite-preview-panel">
    {frame ? <>
      {frame.status !== "processed" && (
        <div className="panel-body"><StateNotice variant="no-imagery" title="NO IMAGE STORED" message={`cyclone_database records this ${frame.source} frame${frame.datasetLabel ? ` (labelled ${frame.datasetLabel})` : ""} but stores no image for it.`} /></div>
      )}
      <div className="satellite-meta-grid"><div><span className="metric-label">SOURCE</span><strong><Satellite size={14} />{frame.source}</strong></div><div><span className="metric-label">CHANNEL</span><strong>{frame.channel ?? "—"}</strong></div><div><span className="metric-label">CAPTURED</span><strong><TimerReset size={13} />{formatObservedAt(frame.capturedAt)}</strong></div></div>
    </> : <div className="panel-body"><StateNotice variant="no-imagery" title="NO SATELLITE RECORDS" message="cyclone_database holds no satellite frame record for this region." /></div>}
    <div className="panel-footer-link"><span>{frame ? <>{frame.region}{frame.resolutionKm != null ? ` · ~${frame.resolutionKm} km resolution` : ""}{frame.status !== "processed" ? <> · <ImageOff size={12} /> no image</> : null}</> : "Satellite intelligence"}</span><button type="button" onClick={onOpen} data-testid="satellite-open-button"><ExternalLink size={13} />Open intelligence</button></div>
  </Panel>;
}
