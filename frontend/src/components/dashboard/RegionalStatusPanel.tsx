import { ChevronRight } from "lucide-react";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatWind, usePreferences } from "@/lib/preferences";
import { padCount, resolveCycloneArea } from "@/lib/regions";
import type { DataSource } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";
import type { Region } from "@/types/region";

interface RegionalStatusPanelProps {
  regions: Region[];
  cyclones: CycloneData[];
  selectedId?: string;
  source?: DataSource;
  onSelect: (cycloneId: string) => void;
  onOpenRegion: (regionId: string) => void;
}

const strength = (cyclone: CycloneData) => cyclone.peakWindKmh ?? cyclone.windKmh ?? -1;

/** Every monitored region with its most recent storms from the database; picking one focuses the dashboard on it. */
export default function RegionalStatusPanel({ regions, cyclones, selectedId, source, onSelect, onOpenRegion }: RegionalStatusPanelProps) {
  const { preferences } = usePreferences();
  return (
    <Panel eyebrow="REGIONAL STATUS" title="Recent storms by region" action={<DataSourceBadge source={source} />} data-testid="regional-status-panel">
      <div className="regional-status-list">
        {regions.map((region) => {
          const systems = cyclones.filter((cyclone) => resolveCycloneArea(regions, cyclone)?.regionId === region.id).sort((a, b) => strength(b) - strength(a));
          const active = systems.filter((cyclone) => cyclone.status === "active").length;
          return (
            <div className="regional-status-row" key={region.id} data-testid={`regional-status-${region.id}`}>
              <button type="button" className="regional-status-head" onClick={() => onOpenRegion(region.id)} title={`Open ${region.name} in Satellite Intelligence`}>
                <span className="regional-status-name"><strong>{region.name}</strong><small>IBTrACS {region.basins.join(" + ")} · {active} active</small></span>
                <span className="regional-status-count">{padCount(systems.length)}<small>RECENT</small></span>
                <ChevronRight size={14} />
              </button>
              <div className="regional-status-systems">
                {systems.length === 0 && <span className="regional-status-empty">No recent storms in the database</span>}
                {systems.slice(0, 8).map((cyclone) => (
                  <button
                    type="button"
                    key={cyclone.id}
                    className={`chip ${cyclone.id === selectedId ? "chip-active" : ""}`}
                    aria-pressed={cyclone.id === selectedId}
                    onClick={() => onSelect(cyclone.id)}
                    title={`${cyclone.code} · peak ${formatWind(cyclone.peakWindKmh, preferences.windUnit)}`}
                    data-testid={`dashboard-select-${cyclone.id}`}
                  >
                    <span className={`status-dot status-dot-${cyclone.status === "active" ? "amber" : "muted"}`} />{cyclone.name} {cyclone.season ?? ""}<b>{formatWind(cyclone.peakWindKmh ?? cyclone.windKmh, preferences.windUnit)}</b>
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
