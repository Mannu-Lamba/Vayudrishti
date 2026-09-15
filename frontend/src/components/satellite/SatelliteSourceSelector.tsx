import { formatLongitude } from "@/lib/geo";
import { TIER_LABEL } from "@/lib/satellite";
import type { SatelliteSource, SatelliteSourceCoverage } from "@/types/region";

interface SatelliteSourceSelectorProps {
  sources: SatelliteSource[];
  coverage: SatelliteSourceCoverage[];
  value?: string;
  onChange: (sourceId: string) => void;
}

// Options come from the region's availability config, never from JSX literals.
export default function SatelliteSourceSelector({ sources, coverage, value, onChange }: SatelliteSourceSelectorProps) {
  if (!sources.length) {
    return <select className="vd-select" disabled aria-label="Satellite source" data-testid="satellite-source-select"><option>No source available</option></select>;
  }
  const selected = sources.find((source) => source.id === value);
  const selectedCoverage = coverage.find((entry) => entry.sourceId === value);
  return (
    <div className="sat-source">
      <select className="vd-select" value={value} onChange={(event) => onChange(event.target.value)} aria-label="Satellite source" data-testid="satellite-source-select">
        {sources.map((source) => {
          const tier = coverage.find((entry) => entry.sourceId === source.id)?.tier;
          return <option key={source.id} value={source.id}>{`${source.name}${source.serviceSlot ? ` (${source.serviceSlot})` : ""}${tier ? ` — ${TIER_LABEL[tier]}` : ""}`}</option>;
        })}
      </select>
      {selected && (
        <div className="sat-source-meta">
          {selectedCoverage && <span className={`tier-badge tier-${selectedCoverage.tier}`}>{TIER_LABEL[selectedCoverage.tier]}</span>}
          <span>{selected.agency}</span>
          {selected.subSatelliteLongitude != null && <span>SSP {formatLongitude(selected.subSatelliteLongitude)}</span>}
          {selected.cadenceMinutes != null && <span>{selected.cadenceMinutes} min scans</span>}
          {selectedCoverage?.note && <span className="sat-source-note">{selectedCoverage.note}</span>}
        </div>
      )}
    </div>
  );
}
