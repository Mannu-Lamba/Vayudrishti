import Panel from "@/components/common/Panel";
import RegionStats from "./RegionStats";
import { formatWind, usePreferences } from "@/lib/preferences";
import { padCount, summaryFor, type RegionSummaryIndex, type SelectionDetails } from "@/lib/regions";
import type { RegionSelection, SatelliteSource, SatelliteSourceCoverage } from "@/types/region";

interface RegionOverviewProps {
  details: SelectionDetails;
  selection: RegionSelection;
  summaries: RegionSummaryIndex;
  sources: SatelliteSource[];
  coverage: SatelliteSourceCoverage[];
  latestFrame?: string;
  onSelectSubregion: (subregionId: string | undefined) => void;
}

/**
 * Region context: what the view is, how it maps onto the dataset (UI region ≠ IBTrACS basin),
 * and — for regions with sub-views — one indicator tile per subregion to drill into.
 */
export default function RegionOverview({ details, selection, summaries, sources, coverage, latestFrame, onSelectSubregion }: RegionOverviewProps) {
  const { preferences } = usePreferences();
  const region = details.region;
  if (!region) return null;
  const subregions = region.subregions ?? [];
  const isPacificOverview = region.emphasis === "overview" && !selection.subregionId;
  const view = summaryFor(summaries, selection);
  const eyebrow = isPacificOverview ? "GLOBAL PACIFIC OVERVIEW" : region.emphasis === "primary" ? "PRIMARY THEATRE / REGION CONTEXT" : "REGION CONTEXT";
  const sourceNames = sources
    .map((source) => `${source.name}${coverage.find((entry) => entry.sourceId === source.id)?.tier === "limb" ? " (limb)" : ""}`)
    .join(" · ");

  return (
    <Panel
      className={`region-overview region-overview-${region.emphasis}`}
      eyebrow={eyebrow}
      title={details.path}
      action={<span className="mock-badge" data-testid="region-basin-badge">DATA LAYER · IBTrACS {details.basins.join(" + ")}</span>}
      data-testid="region-overview"
    >
      <div className="region-overview-body">
        <div className="region-overview-copy">
          {details.description && <p>{details.description}</p>}
          <dl className="region-facts">
            <div><dt>UI view</dt><dd data-testid="region-ui-view">{selection.regionId}{selection.subregionId ? ` › ${selection.subregionId}` : ""}</dd></div>
            <div><dt>Dataset basin</dt><dd data-testid="region-dataset-basin">IBTrACS BASIN = {details.basins.join(" + ") || "—"}</dd></div>
            <div><dt>Warning centre</dt><dd>{details.rsmc ?? "—"}</dd></div>
            <div><dt>Season</dt><dd>{details.season ?? "—"}</dd></div>
            <div><dt>Sources</dt><dd>{sourceNames || "None configured"}</dd></div>
          </dl>
        </div>
        <div className="region-overview-side">
          <RegionStats
            stats={[
              { label: "Active systems", value: padCount(view.activeSystems), tone: view.activeSystems ? "amber" : undefined },
              { label: "Strongest", value: view.strongestCode ?? "—", detail: view.maxWindKmh != null ? formatWind(view.maxWindKmh, preferences.windUnit) : "No active system" },
              { label: "Satellite sources", value: padCount(sources.length) },
              { label: "Latest frame", value: latestFrame ?? "—", tone: "cyan" },
            ]}
          />
          {subregions.length > 0 && (
            <div className="subregion-tiles" data-testid="subregion-tiles">
              {subregions.map((subregion) => {
                const summary = summaryFor(summaries, { regionId: region.id, subregionId: subregion.id });
                const active = subregion.id === selection.subregionId;
                return (
                  <button
                    type="button"
                    key={subregion.id}
                    className={`subregion-tile ${active ? "subregion-tile-active" : ""}`}
                    aria-pressed={active}
                    onClick={() => onSelectSubregion(active ? undefined : subregion.id)}
                    data-testid={`subregion-tile-${subregion.id}`}
                  >
                    <span className="subregion-tile-head"><span>{subregion.name.toUpperCase()}</span><span className="subregion-tile-basin">{subregion.basins.join(" + ")}</span></span>
                    <span className="subregion-tile-count" data-testid={`subregion-tile-${subregion.id}-count`}>{padCount(summary.activeSystems)}</span>
                    <small>{summary.activeSystems ? `Strongest ${summary.strongestCode} · ${formatWind(summary.maxWindKmh ?? 0, preferences.windUnit)}` : "No active systems"}</small>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
