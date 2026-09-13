import Panel from "@/components/common/Panel";
import SubregionSelector from "./SubregionSelector";
import SatelliteSourceSelector from "./SatelliteSourceSelector";
import ChannelSelector from "./ChannelSelector";
import type { RegionSummaryIndex } from "@/lib/regions";
import type { Region, SatelliteSource, SatelliteSourceCoverage } from "@/types/region";
import type { SatelliteChannelId, SatelliteChannelSpec } from "@/types/satellite";

interface SatelliteControlsProps {
  region: Region;
  subregionId?: string;
  summaries: RegionSummaryIndex;
  onSubregionChange: (subregionId: string | undefined) => void;
  sources: SatelliteSource[];
  coverage: SatelliteSourceCoverage[];
  sourceId?: string;
  onSourceChange: (sourceId: string) => void;
  channels: SatelliteChannelSpec[];
  channelId: SatelliteChannelId;
  onChannelChange: (channel: SatelliteChannelId) => void;
}

/** Subregion → source → channel, in the order an operator narrows the view. */
export default function SatelliteControls(props: SatelliteControlsProps) {
  const { region, subregionId, summaries, onSubregionChange, sources, coverage, sourceId, onSourceChange, channels, channelId, onChannelChange } = props;
  const source = sources.find((candidate) => candidate.id === sourceId);
  return (
    <Panel className="sat-controls-panel" data-testid="satellite-controls">
      <div className="sat-controls">
        <div className="sat-control">
          <span className="sat-control-label">SUBREGION <b>{region.name.toUpperCase()}</b></span>
          <SubregionSelector region={region} value={subregionId} summaries={summaries} onChange={onSubregionChange} />
        </div>
        <div className="sat-control">
          <span className="sat-control-label">SATELLITE SOURCE <b>{sources.length} AVAILABLE</b></span>
          <SatelliteSourceSelector sources={sources} coverage={coverage} value={sourceId} onChange={onSourceChange} />
        </div>
        <div className="sat-control">
          <span className="sat-control-label">CHANNEL</span>
          <ChannelSelector channels={channels} source={source} value={channelId} onChange={onChannelChange} />
        </div>
      </div>
    </Panel>
  );
}
