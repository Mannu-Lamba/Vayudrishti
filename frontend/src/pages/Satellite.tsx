import { BrainCircuit, MapPinned, Satellite as SatelliteIcon } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ApiErrorState from "@/components/common/ApiErrorState";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import StateNotice from "@/components/common/StateNotice";
import CycloneMap from "@/components/map/CycloneMap";
import RegionOverview from "@/components/region/RegionOverview";
import RegionSelector from "@/components/satellite/RegionSelector";
import SatelliteControls from "@/components/satellite/SatelliteControls";
import SatelliteTimeline, { type TimelineEntry } from "@/components/satellite/SatelliteTimeline";
import SatelliteViewer from "@/components/satellite/SatelliteViewer";
import SatelliteComparison, { type ComparisonCard } from "@/components/satellite/SatelliteComparison";
import SatelliteMetadata from "@/components/satellite/SatelliteMetadata";
import RegionalCycloneStatus from "@/components/satellite/RegionalCycloneStatus";
import { useCycloneMapData } from "@/hooks/useCycloneMap";
import { useCyclones, useRegionalObservation } from "@/hooks/useCyclones";
import { useRegions } from "@/hooks/useRegions";
import { useSatelliteCatalog, useSatelliteObservation, useSatelliteObservations } from "@/hooks/useSatellite";
import { forecastLabelFor, mapStatusFor, toMapMarkers } from "@/lib/mapScene";
import { cycloneInSelection, describeSelection, resolveSelection, sectorsFor, selectionKey, summarizeRegions } from "@/lib/regions";
import { routeTo } from "@/lib/routes";
import { DEFAULT_CHANNEL, formatFrameTimestamp, formatUtcClock, isChannelId, UNAVAILABLE_SHORT } from "@/lib/satellite";
import { useSearchParamState } from "@/lib/searchParams";
import { recordClientAudit } from "@/services/access";
import type { SatelliteChannelId, SatelliteObservation } from "@/types/satellite";

function timelineStatus(observation?: SatelliteObservation): TimelineEntry["status"] {
  if (!observation) return "missing";
  if (observation.available) return "ready";
  if (observation.unavailableReason === "local_night") return "night";
  if (observation.unavailableReason === "processing") return "processing";
  return "missing";
}

// All selection state lives in the URL (?region, subregion, source, channel, t, cyclone):
// switching never reloads the page, and "View on map" can hand the same context to /cyclones.
export default function Satellite() {
  const navigate = useNavigate();
  const [params, updateParams] = useSearchParamState();

  const regionsQuery = useRegions();
  const regions = useMemo(() => regionsQuery.data ?? [], [regionsQuery.data]);
  const cyclonesQuery = useCyclones();
  const cycloneList = useMemo(() => cyclonesQuery.data ?? [], [cyclonesQuery.data]);
  const selection = resolveSelection(regions, params.get("region"), params.get("subregion"));
  const key = selectionKey(selection);
  const details = describeSelection(regions, selection);
  const summaries = useMemo(() => summarizeRegions(regions, cycloneList), [regions, cycloneList]);

  // ── Satellite catalog for the sector (sources + frame metadata) ──
  const catalogQuery = useSatelliteCatalog(selection);
  const catalog = catalogQuery.data;
  const sources = catalog?.sources ?? [];
  const coverage = catalog?.availability?.sources ?? [];
  const channels = catalog?.channels ?? [];
  const slots = catalog?.slots ?? [];

  // ?source= accepts an id (insat-3d) or a display name (INSAT-3D).
  const requestedSource = params.get("source")?.toLowerCase();
  const sourceId = sources.find((source) => source.id === requestedSource || source.name.toLowerCase() === requestedSource)?.id ?? catalog?.availability?.defaultSourceId;
  const source = sources.find((candidate) => candidate.id === sourceId);
  const requestedChannel = params.get("channel");
  const channelId: SatelliteChannelId = isChannelId(requestedChannel) ? requestedChannel : DEFAULT_CHANNEL;
  const channel = channels.find((candidate) => candidate.id === channelId);
  const slot = slots.find((candidate) => candidate.id === params.get("t")) ?? slots[slots.length - 1];
  const slotId = slot?.id;

  const findObservation = (candidateSource: string | undefined, candidateSlot: string | undefined) =>
    catalog?.observations.find((observation) => observation.source === candidateSource && observation.channel === channelId && observation.slotId === candidateSlot);
  const observation = findObservation(sourceId, slotId);

  // ── Primary frame (keeps the previous image on screen while the next one loads) ──
  const frameQuery = useSatelliteObservation(observation?.available ? observation.id : undefined, { keepPrevious: true });

  const timelineEntries: TimelineEntry[] = slots.map((candidate) => {
    const entry = findObservation(sourceId, candidate.id);
    return {
      id: candidate.id,
      label: candidate.label,
      status: timelineStatus(entry),
      detail: entry ? `${formatUtcClock(entry.timestamp)} scan · ${entry.available ? "frame ready" : UNAVAILABLE_SHORT[entry.unavailableReason ?? "scan_gap"]}` : "No frame",
    };
  });

  const latestObservation = catalog?.observations
    .filter((candidate) => candidate.source === sourceId && candidate.available)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0];

  // ── Regional cyclone observation at the selected slot ──
  const observationQuery = useRegionalObservation(selection, slotId);
  const regional = observationQuery.data && observationQuery.data.regionId === selection.regionId && observationQuery.data.subregionId === selection.subregionId
    ? observationQuery.data
    : undefined;
  const requestedCyclone = params.get("cyclone");
  const focusedId = regional?.systems.some((system) => system.cycloneId === requestedCyclone) ? requestedCyclone ?? undefined : regional?.strongest?.cycloneId;

  // Every system in the region (the map shows the whole region with subregions outlined).
  const regionId = selection.regionId;
  const mapMarkers = useMemo(() => toMapMarkers(cycloneList.filter((cyclone) => cycloneInSelection(regions, cyclone, { regionId }))), [cycloneList, regions, regionId]);
  const mapData = useCycloneMapData(focusedId);
  const sectors = useMemo(() => sectorsFor(details.region, selection.subregionId), [details.region, selection.subregionId]);

  // ── Multi-source comparison at the same slot and channel ──
  const comparisonEntries = coverage.map((entry) => ({ entry, source: sources.find((candidate) => candidate.id === entry.sourceId), observation: findObservation(entry.sourceId, slotId) }));
  const comparisonFrames = useSatelliteObservations(comparisonEntries.map(({ observation: candidate }) => (candidate?.available ? candidate.id : undefined)));
  const comparisonCards: ComparisonCard[] = comparisonEntries.flatMap(({ entry, source: candidateSource, observation: candidate }, index) => (candidateSource
    ? [{ source: candidateSource, tier: entry.tier, note: entry.note, observation: candidate, frame: comparisonFrames[index]?.data, isLoading: comparisonFrames[index]?.fetching ?? false }]
    : []));

  // ── Handlers ──
  const changeRegion = (nextRegionId: string) => {
    if (nextRegionId === selection.regionId && !selection.subregionId) return;
    updateParams({ region: nextRegionId, subregion: null, source: null, cyclone: null });
  };
  const changeSubregion = (subregionId: string | undefined) => updateParams({ region: selection.regionId, subregion: subregionId ?? null });
  const changeSource = (nextSourceId: string) => updateParams({ source: nextSourceId });
  const changeChannel = (nextChannel: SatelliteChannelId) => {
    if (nextChannel === channelId) return;
    updateParams({ channel: nextChannel });
    const label = channels.find((candidate) => candidate.id === nextChannel)?.label ?? nextChannel;
    recordClientAudit({ action: "satellite.layer_changed", target: label, details: { satellite: source?.name ?? null, region: selection.regionId, subregion: selection.subregionId ?? null } });
  };
  const jumpToAvailable = () => {
    const current = slots.findIndex((candidate) => candidate.id === slotId);
    const nearest = slots
      .map((candidate, index) => ({ candidate, index, entry: findObservation(sourceId, candidate.id) }))
      .filter(({ entry }) => entry?.available)
      .sort((a, b) => Math.abs(a.index - current) - Math.abs(b.index - current) || b.index - a.index)[0];
    if (nearest) updateParams({ t: nearest.candidate.id });
  };
  const context = { region: selection.regionId, subregion: selection.subregionId, cyclone: focusedId, source: sourceId };

  return (
    <div className="page-stack sat-page" data-testid="satellite-page">
      <div className="page-intro-row">
        <div>
          <div className="section-kicker"><SatelliteIcon size={13} /> MULTI-REGION SATELLITE OBSERVATION</div>
          <h2 className="page-heading">Satellite intelligence</h2>
          <p className="page-subheading">{details.description} Sources, channels and frames follow the selected region.</p>
        </div>
        <div className="page-intro-actions">
          <DataSourceBadge source={catalogQuery.source} />
          <button type="button" className="secondary-action" onClick={() => navigate(routeTo.prediction(context))} disabled={!focusedId} data-testid="satellite-open-prediction"><BrainCircuit size={14} /> AI PREDICTION</button>
          <button type="button" className="primary-action" onClick={() => navigate(routeTo.cyclones(context))} data-testid="view-on-map-button"><MapPinned size={14} /> VIEW ON MAP</button>
        </div>
      </div>

      {regionsQuery.error ? <ApiErrorState error={regionsQuery.error} onRetry={regionsQuery.refetch} subject="regions" /> : null}

      <RegionSelector regions={regions} value={selection} summaries={summaries} onChange={changeRegion} />

      <RegionOverview
        details={details}
        selection={selection}
        summaries={summaries}
        sources={sources}
        coverage={coverage}
        latestFrame={latestObservation ? formatUtcClock(latestObservation.timestamp) : undefined}
        onSelectSubregion={changeSubregion}
      />

      {details.region && (
        <SatelliteControls
          region={details.region}
          subregionId={selection.subregionId}
          summaries={summaries}
          onSubregionChange={changeSubregion}
          sources={sources}
          coverage={coverage}
          sourceId={sourceId}
          onSourceChange={changeSource}
          channels={channels}
          channelId={channelId}
          onChannelChange={changeChannel}
        />
      )}

      <SatelliteTimeline
        entries={timelineEntries}
        value={slotId}
        onChange={(id) => updateParams({ t: id })}
        readout={formatFrameTimestamp(slot?.timestamp)}
        heading={`TIMELINE · ${source?.name ?? "—"} ${channel?.shortLabel ?? ""} · UTC`}
      />

      {catalogQuery.error ? <ApiErrorState error={catalogQuery.error} onRetry={catalogQuery.refetch} subject="satellite imagery" /> : null}

      <div className="sat-main-grid">
        <SatelliteViewer
          key={key}
          observation={observation}
          frame={frameQuery.data}
          isFetching={frameQuery.fetching}
          isCatalogLoading={catalogQuery.loading}
          hasSource={sources.length > 0}
          source={source}
          channel={channel}
          regionLabel={details.region?.name ?? details.label}
          subregionLabel={details.subregion?.name}
          focusedCycloneId={focusedId}
          onSwitchChannel={changeChannel}
          onJumpToAvailable={jumpToAvailable}
        />
        <div className="sat-side-stack">
          <RegionalCycloneStatus
            observation={regional}
            isLoading={observationQuery.loading}
            regionLabel={details.label}
            slotLabel={slot?.label}
            season={details.season}
            focusedId={focusedId}
            onFocus={(cycloneId) => updateParams({ cyclone: cycloneId })}
          />
          <CycloneMap
            cyclones={mapMarkers}
            selectedCycloneId={focusedId}
            onCycloneSelect={(cycloneId) => updateParams({ cyclone: cycloneId })}
            scene={mapData.scene}
            dataSource={cyclonesQuery.source}
            districts={mapData.districts}
            status={mapStatusFor(cyclonesQuery, mapData)}
            forecastLabel={forecastLabelFor(mapData.forecastSource)}
            variant="compact"
            showTimeline={false}
            viewport={details.viewport}
            followCyclone={false}
            eyebrow={`GEOSPATIAL / ${details.path.toUpperCase()}`}
            title="Regional map"
            tags={details.landmarks.slice(0, 3).map((landmark) => landmark.label)}
            sectors={sectors}
          />
        </div>
      </div>

      <SatelliteComparison cards={comparisonCards} activeSourceId={sourceId} channel={channel} slotLabel={slot?.label} onSelect={changeSource} />

      <div className="sat-bottom-grid">
        <SatelliteMetadata observation={observation} source={source} channel={channel} details={details} />
        {!catalogQuery.loading && !catalogQuery.error && !sources.length && (
          <StateNotice variant="empty" title="NO SATELLITE RECORDS" message={`cyclone_database holds no satellite frame records for the ${details.label}.`} />
        )}
      </div>
    </div>
  );
}
