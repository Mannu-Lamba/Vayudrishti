import Panel from "@/components/common/Panel";
import RegionSelector from "@/components/satellite/RegionSelector";
import SubregionSelector from "@/components/satellite/SubregionSelector";
import type { RegionSummaryIndex } from "@/lib/regions";
import type { CycloneData } from "@/types/cyclone";
import type { Region, RegionSelection } from "@/types/region";

interface PredictionSelectorProps {
  regions: Region[];
  region?: Region;
  selection: RegionSelection;
  summaries: RegionSummaryIndex;
  cyclones: CycloneData[];
  cycloneId?: string;
  onRegionChange: (regionId: string) => void;
  onSubregionChange: (subregionId: string | undefined) => void;
  onCycloneChange: (cycloneId: string) => void;
}

/** Region → subregion → cyclone, all options from typed data. */
export default function PredictionSelector({ regions, region, selection, summaries, cyclones, cycloneId, onRegionChange, onSubregionChange, onCycloneChange }: PredictionSelectorProps) {
  return (
    <Panel className="pred-selector-panel" data-testid="prediction-selector">
      <div className="pred-selector">
        <div className="sat-control">
          <span className="sat-control-label">REGION</span>
          <RegionSelector compact regions={regions} value={selection} summaries={summaries} onChange={onRegionChange} />
        </div>
        <div className="sat-control">
          <span className="sat-control-label">SUBREGION</span>
          {region ? <SubregionSelector region={region} value={selection.subregionId} summaries={summaries} onChange={onSubregionChange} /> : <div className="sat-control-note">No region selected</div>}
        </div>
        <div className="sat-control">
          <span className="sat-control-label">CYCLONE <b>{cyclones.length} IN VIEW</b></span>
          <select
            className="vd-select"
            value={cycloneId ?? ""}
            disabled={!cyclones.length}
            onChange={(event) => onCycloneChange(event.target.value)}
            aria-label="Cyclone"
            data-testid="prediction-cyclone-select"
          >
            {!cyclones.length && <option value="">No active cyclones in this region</option>}
            {/* One string per option: mixed text/expression children get wrapped in <span>s by the dev visual-edits plugin, which <option> cannot contain. */}
            {cyclones.map((cyclone) => <option key={cyclone.id} value={cyclone.id}>{`${cyclone.code} · ${cyclone.name} — ${cyclone.category}`}</option>)}
          </select>
        </div>
      </div>
    </Panel>
  );
}
