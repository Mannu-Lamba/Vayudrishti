import { ChevronRight } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { padCount, resolveCycloneArea } from "@/lib/regions";
import type { DataSource } from "@/types/api";
import type { CycloneData, RiskLevel } from "@/types/cyclone";
import type { Region } from "@/types/region";

const RISK_TONE: Record<RiskLevel, string> = { severe: "red", high: "amber", moderate: "cyan", low: "green" };

interface RegionalStatusPanelProps {
  regions: Region[];
  cyclones: CycloneData[];
  selectedId?: string;
  source?: DataSource;
  onSelect: (cycloneId: string) => void;
  onOpenRegion: (regionId: string) => void;
}

/** Every monitored region with its active systems; picking a system focuses the dashboard on it. */
export default function RegionalStatusPanel({ regions, cyclones, selectedId, source, onSelect, onOpenRegion }: RegionalStatusPanelProps) {
  return (
    <Panel eyebrow="REGIONAL STATUS" title="Active systems by region" action={<DataSourceBadge source={source} />} data-testid="regional-status-panel">
      <div className="regional-status-list">
        {regions.map((region) => {
          const systems = cyclones.filter((cyclone) => resolveCycloneArea(regions, cyclone)?.regionId === region.id).sort((a, b) => b.windKmh - a.windKmh);
          return (
            <div className="regional-status-row" key={region.id} data-testid={`regional-status-${region.id}`}>
              <button type="button" className="regional-status-head" onClick={() => onOpenRegion(region.id)} title={`Open ${region.name} in Satellite Intelligence`}>
                <span className="regional-status-name"><strong>{region.name}</strong><small>IBTrACS {region.basins.join(" + ")}</small></span>
                <span className="regional-status-count">{padCount(systems.length)}<small>ACTIVE</small></span>
                <ChevronRight size={14} />
              </button>
              <div className="regional-status-systems">
                {systems.length === 0 && <span className="regional-status-empty">No active cyclones</span>}
                {systems.map((cyclone) => (
                  <button
                    type="button"
                    key={cyclone.id}
                    className={`chip ${cyclone.id === selectedId ? "chip-active" : ""}`}
                    aria-pressed={cyclone.id === selectedId}
                    onClick={() => onSelect(cyclone.id)}
                    data-testid={`dashboard-select-${cyclone.id}`}
                  >
                    <span className={`status-dot status-dot-${RISK_TONE[cyclone.riskLevel]}`} />{cyclone.code}<b>{cyclone.windKmh} km/h</b>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
