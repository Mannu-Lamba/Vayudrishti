import { summaryFor, type RegionSummaryIndex } from "@/lib/regions";
import type { Region } from "@/types/region";

interface SubregionSelectorProps {
  region: Region;
  value?: string;
  summaries: RegionSummaryIndex;
  /** `undefined` = region-wide / overview. */
  onChange: (subregionId: string | undefined) => void;
}

export default function SubregionSelector({ region, value, summaries, onChange }: SubregionSelectorProps) {
  const subregions = region.subregions ?? [];
  if (!subregions.length) {
    return <div className="sat-control-note" data-testid="subregion-none">Basin-wide sector · no sub-views configured</div>;
  }
  const regionCount = summaryFor(summaries, { regionId: region.id }).activeSystems;
  return (
    <div className="chip-row" role="group" aria-label="Subregion" data-testid="subregion-selector">
      <button
        type="button"
        className={`chip ${!value ? "chip-active" : ""}`}
        aria-pressed={!value}
        onClick={() => onChange(undefined)}
        data-testid="subregion-chip-overview"
      >
        {region.emphasis === "overview" ? "Overview" : "Full region"}<b>{regionCount}</b>
      </button>
      {subregions.map((subregion) => {
        const active = subregion.id === value;
        return (
          <button
            type="button"
            key={subregion.id}
            className={`chip ${active ? "chip-active" : ""}`}
            aria-pressed={active}
            onClick={() => onChange(subregion.id)}
            data-testid={`subregion-chip-${subregion.id}`}
          >
            {subregion.name}<b>{summaryFor(summaries, { regionId: region.id, subregionId: subregion.id }).activeSystems}</b>
          </button>
        );
      })}
    </div>
  );
}
