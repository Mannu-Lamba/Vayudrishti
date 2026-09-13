import { padCount, summaryFor, type RegionSummaryIndex } from "@/lib/regions";
import type { Region, RegionSelection } from "@/types/region";

interface RegionSelectorProps {
  regions: Region[];
  value: RegionSelection;
  summaries: RegionSummaryIndex;
  onChange: (regionId: string) => void;
  /** Slim single-row variant for secondary pages (Cyclone Monitor). */
  compact?: boolean;
}

export default function RegionSelector({ regions, value, summaries, onChange, compact = false }: RegionSelectorProps) {
  return (
    <div className={`region-selector ${compact ? "region-selector-compact" : ""}`} role="group" aria-label="Region" data-testid="region-selector">
      {regions.map((region) => {
        const active = region.id === value.regionId;
        const count = summaryFor(summaries, { regionId: region.id }).activeSystems;
        return (
          <button
            type="button"
            key={region.id}
            className={`region-tile region-tile-${region.emphasis} ${active ? "region-tile-active" : ""}`}
            aria-pressed={active}
            onClick={() => onChange(region.id)}
            data-testid={`region-tile-${region.id}`}
          >
            <span className="region-tile-top">
              <span>{region.shortName}</span>
              {region.emphasis === "primary" && <span className="region-tile-flag">PRIMARY THEATRE</span>}
              {region.emphasis === "overview" && <span className="region-tile-flag region-tile-flag-cyan">GLOBAL OVERVIEW</span>}
            </span>
            <strong>{region.name}</strong>
            {!compact && <small>{region.subregions?.length ? region.subregions.map((subregion) => subregion.name).join(" · ") : "Basin-wide view"}</small>}
            <span className="region-tile-foot">
              <span>DATA · IBTrACS {region.basins.join(" + ")}</span>
              <b data-testid={`region-tile-${region.id}-count`}>{padCount(count)} ACTIVE</b>
            </span>
          </button>
        );
      })}
    </div>
  );
}
