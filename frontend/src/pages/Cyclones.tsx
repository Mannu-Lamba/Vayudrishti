import { BrainCircuit, ChevronRight, CircleDot, LocateFixed, MapPin, Satellite, Wind } from "lucide-react";
import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ApiErrorState from "@/components/common/ApiErrorState";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import LoadingBlock from "@/components/common/LoadingBlock";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import CycloneDetailPanel from "@/components/cyclones/CycloneDetailPanel";
import CycloneMap from "@/components/map/CycloneMap";
import RegionSelector from "@/components/satellite/RegionSelector";
import SubregionSelector from "@/components/satellite/SubregionSelector";
import { categoryColor } from "@/config/cycloneCategories";
import { useCyclone } from "@/hooks/useCyclone";
import { useCycloneMapData } from "@/hooks/useCycloneMap";
import { useCyclones } from "@/hooks/useCyclones";
import { useMlAssessment } from "@/hooks/usePrediction";
import { useRegions } from "@/hooks/useRegions";
import { formatLatitude } from "@/lib/geo";
import { forecastLabelFor, mapStatusFor, toMapMarkers } from "@/lib/mapScene";
import { formatWind, usePreferences } from "@/lib/preferences";
import { cycloneInSelection, describeSelection, padCount, resolveCycloneArea, resolveSelection, sectorsFor, summarizeRegions } from "@/lib/regions";
import { routeTo } from "@/lib/routes";
import { useSearchParamState } from "@/lib/searchParams";
import { toIsoTimestamp } from "@/lib/time";
import { recordClientAudit } from "@/services/access";
import type { CycloneData } from "@/types/cyclone";
import type { RegionSelection } from "@/types/region";

const observedMs = (cyclone: CycloneData) => Date.parse(toIsoTimestamp(cyclone.observedAt));

// State in the URL: ?region, ?subregion and ?cyclone (id or code, e.g. /cyclones?cyclone=VD-001).
// Without ?region the map opens on the requested cyclone's own region/subregion. Dashboard,
// satellite and prediction link here with the same context.
export default function Cyclones() {
  const navigate = useNavigate();
  const { preferences } = usePreferences();
  const [params, updateParams] = useSearchParamState();
  const regionsQuery = useRegions();
  const regions = useMemo(() => regionsQuery.data ?? [], [regionsQuery.data]);
  const allQuery = useCyclones();
  const allCyclones = useMemo(() => allQuery.data ?? [], [allQuery.data]);

  const requestedParam = params.get("cyclone");
  const requested = requestedParam?.toLowerCase();
  const requestedCyclone = requested ? allCyclones.find((cyclone) => cyclone.id === requested || cyclone.code.toLowerCase() === requested) : undefined;
  const selection = !params.get("region") && requestedCyclone
    ? resolveCycloneArea(regions, requestedCyclone) ?? resolveSelection(regions, null, null)
    : resolveSelection(regions, params.get("region"), params.get("subregion"));
  const details = describeSelection(regions, selection);
  const summaries = useMemo(() => summarizeRegions(regions, allCyclones), [regions, allCyclones]);

  // GET /api/cyclones?region=…&subregion=… — only the systems in view are requested.
  const regionalQuery = useCyclones(selection);
  const cyclones = useMemo(() => regionalQuery.data ?? [], [regionalQuery.data]);
  const selected: CycloneData | null = cyclones.find((cyclone) => cyclone.id === requestedCyclone?.id) ?? cyclones[0] ?? null;

  // A cyclone that is unknown or outside the selected region/subregion is dropped from the URL.
  const registryReady = regionalQuery.data !== undefined && allQuery.data !== undefined;
  const invalidRequest = Boolean(requestedParam) && registryReady && !cyclones.some((cyclone) => cyclone.id === requestedCyclone?.id);
  useEffect(() => {
    if (invalidRequest) updateParams({ cyclone: null });
  }, [invalidRequest, updateParams]);

  // Selected cyclone: registry record (GET /api/cyclones/{id}), track + forecast, classification.
  const detailQuery = useCyclone(selected?.id);
  const detail = detailQuery.data ?? selected;
  const mapData = useCycloneMapData(selected?.id);
  const assessment = useMlAssessment(selected?.id);
  const area = detail ? resolveCycloneArea(regions, detail) : null;
  const areaDetails = area ? describeSelection(regions, area) : null;

  const markers = useMemo(() => toMapMarkers(cyclones), [cyclones]);
  const sectors = useMemo(() => sectorsFor(details.region, selection.subregionId), [details.region, selection.subregionId]);
  const strongest = useMemo(() => [...cyclones].sort((a, b) => b.windKmh - a.windKmh)[0], [cyclones]);
  const latest = useMemo(() => cyclones.reduce<CycloneData | null>((best, cyclone) => (!best || observedMs(cyclone) > observedMs(best) ? cyclone : best), null), [cyclones]);
  const context = { region: area?.regionId ?? selection.regionId, subregion: area?.subregionId ?? selection.subregionId, cyclone: selected?.id, source: params.get("source") ?? undefined };

  const selectCyclone = (cyclone: CycloneData) => {
    if (cyclone.id === selected?.id) return;
    // Pin the current view so selecting a system never changes the region or subregion.
    updateParams({ region: selection.regionId, subregion: selection.subregionId ?? null, cyclone: cyclone.id });
    recordClientAudit({ action: "cyclone.selected", target: cyclone.code, details: { name: cyclone.name, category: cyclone.category } });
  };
  const selectById = (cycloneId: string) => {
    const cyclone = cyclones.find((candidate) => candidate.id === cycloneId);
    if (cyclone) selectCyclone(cyclone);
  };
  // The selected cyclone survives a region/subregion change only if it is inside the new view.
  const keepSelection = (next: RegionSelection) => (selected && cycloneInSelection(regions, selected, next) ? selected.id : null);
  const changeRegion = (regionId: string) => updateParams({ region: regionId, subregion: null, cyclone: keepSelection({ regionId }), source: null });
  const changeSubregion = (subregionId: string | undefined) => updateParams({ region: selection.regionId, subregion: subregionId ?? null, cyclone: keepSelection({ regionId: selection.regionId, subregionId }) });

  let registry;
  if (regionalQuery.loading || regionsQuery.loading) registry = <div className="panel-body"><LoadingBlock label="LOADING CYCLONE DATA" rows={4} /></div>;
  else if (regionalQuery.error || regionsQuery.error) registry = <div className="panel-body"><ApiErrorState error={regionalQuery.error ?? regionsQuery.error} onRetry={() => { regionsQuery.refetch(); regionalQuery.refetch(); }} title="CYCLONE DATA UNAVAILABLE" message="Unable to retrieve cyclone information." /></div>;
  else if (!cyclones.length) registry = <div className="panel-body"><StateNotice variant="no-systems" message={`No active tropical cyclones in the ${details.label}.${details.season ? ` Season: ${details.season}.` : ""}`} /></div>;
  else registry = <div className="cyclone-list">{cyclones.map((cyclone) => (
    <button type="button" key={cyclone.id} onClick={() => selectCyclone(cyclone)} aria-pressed={selected?.id === cyclone.id} className={`cyclone-list-item ${selected?.id === cyclone.id ? "cyclone-list-item-active" : ""}`} data-testid={`cyclone-list-item-${cyclone.id}`}>
      <div className="list-item-code"><span className="category-dot" style={{ background: categoryColor(cyclone.category) }} />{cyclone.code}<span className="list-item-status">{cyclone.status}</span></div>
      <strong>{cyclone.name}</strong>
      <span className="list-item-meta"><MapPin size={12} />{cyclone.category} · {cyclone.region} · {formatLatitude(cyclone.location.latitude)}</span>
      <div className="list-item-wind"><Wind size={13} />{formatWind(cyclone.windKmh, preferences.windUnit)}<ChevronRight size={14} /></div>
    </button>
  ))}</div>;

  return <div className="page-stack" data-testid="cyclones-page">
    <div className="page-intro-row">
      <div><div className="section-kicker"><LocateFixed size={13} /> TRACKING REGISTRY / {padCount(cyclones.length)} SYSTEMS</div><h2 className="page-heading">Cyclone monitor</h2><p className="page-subheading">Review active systems, motion vectors and observation confidence — {details.path}.</p></div>
      <div className="page-intro-actions">
        <DataSourceBadge source={regionalQuery.source} />
        <button type="button" className="secondary-action" onClick={() => navigate(routeTo.satellite(context))} data-testid="open-satellite-button"><Satellite size={14} /> SATELLITE VIEW</button>
        <button type="button" className="primary-action" onClick={() => navigate(routeTo.prediction(context))} disabled={!selected} data-testid="open-prediction-button"><BrainCircuit size={14} /> AI PREDICTION</button>
      </div>
    </div>
    <div className="region-toolbar" data-testid="cyclones-region-toolbar">
      <RegionSelector compact regions={regions} value={selection} summaries={summaries} onChange={changeRegion} />
      {details.region && <div className="region-toolbar-sub"><span className="sat-control-label">SUBREGION <b>DATA · IBTrACS {details.basins.join(" + ")}</b></span><SubregionSelector region={details.region} value={selection.subregionId} summaries={summaries} onChange={changeSubregion} /></div>}
    </div>
    <div className="monitor-grid">
      <Panel eyebrow="ACTIVE REGISTRY" title={`Systems in ${details.label}`} data-testid="cyclone-registry-panel">
        <div className="registry-stats" data-testid="registry-stats">
          <div><small>Systems</small><strong data-testid="registry-stat-count">{regionalQuery.loading ? "—" : padCount(cyclones.length)}</strong></div>
          <div><small>Strongest</small><strong data-testid="registry-stat-strongest">{strongest ? `${strongest.code} · ${formatWind(strongest.windKmh, preferences.windUnit)}` : "—"}</strong></div>
          <div><small>Data layer</small><strong>IBTrACS {details.basins.join(" + ") || "—"}</strong></div>
        </div>
        {registry}
        <div className="registry-footer"><CircleDot size={13} /> {latest ? `Latest observation ${latest.observedAt}` : "No observations in this view"}</div>
      </Panel>
      <CycloneMap
        cyclones={markers}
        selectedCycloneId={selected?.id}
        onCycloneSelect={selectById}
        scene={mapData.scene}
        dataSource={regionalQuery.source}
        districts={mapData.districts}
        status={mapStatusFor(regionalQuery, mapData)}
        forecastLabel={forecastLabelFor(mapData.forecastSource)}
        variant="full"
        viewport={details.viewport}
        eyebrow={`GEOSPATIAL / ${details.path.toUpperCase()}`}
        tags={details.landmarks.slice(0, 3).map((landmark) => landmark.label)}
        sectors={sectors}
      />
    </div>
    {detail && (
      <CycloneDetailPanel
        cyclone={detail}
        source={detailQuery.source ?? regionalQuery.source}
        regionName={areaDetails?.region?.name}
        subregionName={areaDetails?.subregion?.name}
        track={{ fixes: mapData.trackFixes, loading: mapData.loading, error: mapData.error, onRetry: mapData.refetch }}
        hasPrediction={mapData.hasPrediction}
        classificationAvailable={Boolean(assessment.data?.classification)}
        onViewSatellite={() => navigate(routeTo.satellite(context))}
        onViewClassification={() => navigate(routeTo.prediction(context))}
      />
    )}
  </div>;
}
