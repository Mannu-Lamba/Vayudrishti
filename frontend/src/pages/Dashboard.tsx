import { Activity, AlertOctagon, BellRing, BrainCircuit, Clock3, Database, Globe2, RadioTower, Wind } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import MetricGrid, { type MetricItem } from "@/components/dashboard/MetricGrid";
import CycloneStatus from "@/components/dashboard/CycloneStatus";
import SatellitePreview from "@/components/dashboard/SatellitePreview";
import PredictionSummary from "@/components/dashboard/PredictionSummary";
import RegionalStatusPanel from "@/components/dashboard/RegionalStatusPanel";
import CycloneMap from "@/components/map/CycloneMap";
import ForecastCharts from "@/components/charts/ForecastCharts";
import ApiErrorState from "@/components/common/ApiErrorState";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import LoadingBlock from "@/components/common/LoadingBlock";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import ModelStatusPanel from "@/components/prediction/ModelStatusPanel";
import AnalystWorkspace from "@/components/analyst/AnalystWorkspace";
import { useApiStatus } from "@/hooks/useApiStatus";
import { useCycloneMapData } from "@/hooks/useCycloneMap";
import { useCyclones, useRecentEvents } from "@/hooks/useCyclones";
import { useModelRegistry, usePrediction } from "@/hooks/usePrediction";
import { useRegions } from "@/hooks/useRegions";
import { useLatestSatelliteFrame } from "@/hooks/useSatellite";
import { forecastLabelFor, mapStatusFor, toMapMarkers } from "@/lib/mapScene";
import { defaultRegion, describeSelection, padCount, resolveCycloneArea } from "@/lib/regions";
import { routeTo } from "@/lib/routes";
import { formatUtcClock } from "@/lib/satellite";
import { useSearchParamState } from "@/lib/searchParams";
import { usePreferences, formatPressure, formatWind } from "@/lib/preferences";
import { formatMovement, formatObservedAt } from "@/lib/format";
import type { CycloneData, OperationalEvent } from "@/types/cyclone";

const EVENT_ICON: Record<OperationalEvent["kind"], { icon: typeof AlertOctagon; tone: string }> = {
  alert: { icon: AlertOctagon, tone: "amber" },
  satellite: { icon: RadioTower, tone: "cyan" },
  forecast: { icon: Clock3, tone: "blue" },
  record: { icon: Database, tone: "blue" },
};

const peak = (cyclone: CycloneData) => cyclone.peakWindKmh ?? cyclone.windKmh ?? -1;

function briefing(cyclone: CycloneData): string {
  const state = cyclone.category ? `as a ${cyclone.category.toLowerCase()}` : "with no wind recorded at that fix";
  const motion = cyclone.movementDirection ? `, moving ${formatMovement(cyclone.movementDirection, cyclone.movementSpeedKmh)}` : "";
  const when = cyclone.status === "active" ? "is being tracked" : `was last observed on ${formatObservedAt(cyclone.observedAt)}`;
  return `${cyclone.name} (${cyclone.code}) ${when} ${state}${motion}, in the ${cyclone.location.label}.`;
}

// Everything below arrives through hooks → services; ?cyclone= focuses the dashboard on one system.
// The metrics and the map read the same registry request, so their counts always agree.
export default function Dashboard() {
  const navigate = useNavigate();
  const { preferences } = usePreferences();
  const [params, updateParams] = useSearchParamState();
  const api = useApiStatus();

  const regions = useRegions().data;
  const regionList = useMemo(() => regions ?? [], [regions]);
  const cyclonesQuery = useCyclones();
  const cyclones = useMemo(() => cyclonesQuery.data ?? [], [cyclonesQuery.data]);
  const primaryRegion = defaultRegion(regionList);
  const inPrimary = useMemo(
    () => (primaryRegion ? cyclones.filter((cyclone) => resolveCycloneArea(regionList, cyclone)?.regionId === primaryRegion.id) : []),
    [cyclones, regionList, primaryRegion],
  );
  const strongestPrimary = [...inPrimary].sort((a, b) => peak(b) - peak(a))[0];
  const activePrimary = inPrimary.filter((candidate) => candidate.status === "active");
  const activeAll = cyclones.filter((candidate) => candidate.status === "active");
  const cyclone = cyclones.find((candidate) => candidate.id === params.get("cyclone")) ?? strongestPrimary ?? cyclones[0] ?? null;
  const area = cyclone ? resolveCycloneArea(regionList, cyclone) : null;
  const areaDetails = area ? describeSelection(regionList, area) : null;

  const prediction = usePrediction(cyclone?.id);
  const mapData = useCycloneMapData(cyclone?.id);
  const markers = useMemo(() => toMapMarkers(cyclones), [cyclones]);
  const satellite = useLatestSatelliteFrame(primaryRegion?.id);
  const models = useModelRegistry();
  const events = useRecentEvents(5);

  const forecastable = cyclones.filter((candidate) => candidate.forecastAvailable).length;
  const metrics: MetricItem[] = [
    { id: "active-cyclones", label: "Active cyclones", value: padCount(activePrimary.length), context: `${primaryRegion?.name ?? "Primary region"} · observed in the last 24 h`, icon: Activity, tone: "cyan" },
    { id: "max-wind", label: "Strongest recent storm", value: strongestPrimary && peak(strongestPrimary) > 0 ? formatWind(peak(strongestPrimary), preferences.windUnit) : "—", context: strongestPrimary ? `${strongestPrimary.name} ${strongestPrimary.season ?? ""} / ${strongestPrimary.peakCategory ?? "category unknown"}` : "No storm in the registry", icon: Wind, tone: "amber" },
    { id: "detected-systems", label: "Recent storms listed", value: padCount(cyclones.length), context: `Newest records of cyclone_database, ${regionList.length} regions`, icon: Globe2, tone: "blue" },
    { id: "forecastable", label: "Forecastable storms", value: padCount(forecastable), context: "Full history on the server, so the model can run", icon: BrainCircuit, tone: "blue" },
  ];
  const context = { region: area?.regionId, subregion: area?.subregionId, cyclone: cyclone?.id };
  const lastForecast = prediction.data?.forecast[prediction.data.forecast.length - 1];

  return <div className="page-stack" data-testid="dashboard-page">
    <div className="page-intro-row">
      <div>
        <div className="section-kicker"><RadioTower size={13} /> SITUATION OVERVIEW</div>
        <h2 className="page-heading">{primaryRegion?.name ?? "Operational overview"}</h2>
        <p className="page-subheading">{cyclonesQuery.loading ? "Loading the cyclone registry…" : `${activePrimary.length ? `${activePrimary.length} active system${activePrimary.length === 1 ? "" : "s"} in the ${primaryRegion?.name ?? "primary region"}.` : `No storm has been observed in the last 24 h.`} Showing the ${cyclones.length} most recent storms in cyclone_database, ${inPrimary.length} of them in the ${primaryRegion?.name ?? "primary region"}.`}</p>
      </div>
      <div className="page-intro-meta"><span><Clock3 size={13} /> Next refresh in {preferences.refreshRate === "manual" ? "manual mode" : preferences.refreshRate}</span><span><BellRing size={13} /> {padCount(activeAll.length)} active</span><DataSourceBadge source={cyclonesQuery.source} /></div>
    </div>

    {cyclonesQuery.error ? <ApiErrorState error={cyclonesQuery.error} onRetry={cyclonesQuery.refetch} title="CYCLONE DATA UNAVAILABLE" message="Unable to retrieve cyclone information." /> : <MetricGrid items={metrics} />}

    <div className="dashboard-main-grid">
      <CycloneMap
        cyclones={markers}
        selectedCycloneId={cyclone?.id}
        onCycloneSelect={(cycloneId) => updateParams({ cyclone: cycloneId })}
        scene={mapData.scene}
        dataSource={cyclonesQuery.source}
        districts={mapData.districts}
        status={mapStatusFor(cyclonesQuery, mapData)}
        forecastLabel={forecastLabelFor(mapData.forecastSource)}
        viewport={areaDetails?.viewport}
        eyebrow={`GEOSPATIAL / ${(areaDetails?.path ?? "North Indian Ocean").toUpperCase()}`}
        tags={areaDetails?.landmarks.slice(0, 3).map((landmark) => landmark.label)}
      />
      {cyclone
        ? <CycloneStatus cyclone={cyclone} onOpenMap={() => navigate(routeTo.cyclones(context))} onOpenPrediction={() => navigate(routeTo.prediction(context))} />
        : <Panel className="cyclone-status-panel" eyebrow="PRIMARY SYSTEM" title="No system selected"><div className="panel-body">{cyclonesQuery.loading ? <LoadingBlock label="LOADING CYCLONE DATA" /> : <StateNotice variant="no-systems" />}</div></Panel>}
    </div>

    <div className="dashboard-status-grid">
      <RegionalStatusPanel regions={regionList} cyclones={cyclones} selectedId={cyclone?.id} source={cyclonesQuery.source} onSelect={(id) => updateParams({ cyclone: id })} onOpenRegion={(regionId) => navigate(routeTo.satellite({ region: regionId }))} />
      {models.error
        ? <Panel eyebrow="MODEL STATUS" title="Pipeline readiness"><div className="panel-body"><ApiErrorState error={models.error} onRetry={models.refetch} subject="model status" /></div></Panel>
        : <ModelStatusPanel compact components={models.data?.components ?? []} apiStatus={api.status} source={models.source} />}
    </div>

    <div className="dashboard-secondary-grid">
      <SatellitePreview frame={satellite.data} source={satellite.source} onOpen={() => navigate(routeTo.satellite(context))} />
      <PredictionSummary prediction={prediction.data} source={prediction.source} loading={prediction.loading} error={prediction.error} onRetry={prediction.refetch} onOpen={() => navigate(routeTo.prediction(context))} />
    </div>

    <ForecastCharts prediction={prediction.data} source={prediction.source} loading={prediction.loading} />

    <AnalystWorkspace context={{ storm: cyclone, prediction: prediction.data ?? null, dataSource: prediction.source ?? null }} />

    <div className="dashboard-bottom-grid">
      <Panel eyebrow="ALERT QUEUE" title="Recent events" action={<DataSourceBadge source={events.source} />} data-testid="recent-events-panel">
        <div className="event-list">
          {events.loading && <LoadingBlock label="LOADING EVENTS" />}
          {events.error ? <ApiErrorState error={events.error} onRetry={events.refetch} subject="events" /> : null}
          {events.data?.length === 0 && <StateNotice variant="empty" title="NO RECENT EVENTS" message="Nothing has been reported in this window." />}
          {events.data?.map((event) => {
            const meta = EVENT_ICON[event.kind];
            const Icon = meta.icon;
            return <div className="event-row" key={event.id}><span className={`event-icon event-icon-${meta.tone}`}><Icon size={15} /></span><div><strong>{event.title}</strong><span>{event.source} · {formatUtcClock(event.timestamp)}</span></div><span className={`event-priority ${event.priority === "high" ? "" : "event-priority-muted"}`}>{event.priority === "high" ? "HIGH" : "INFO"}</span></div>;
          })}
        </div>
      </Panel>
      <Panel eyebrow="OPERATOR READOUT" title="Quick briefing" className="briefing-panel" action={<DataSourceBadge source={prediction.source} variant="model" />} data-testid="briefing-panel">
        <p>{cyclone
          ? `${briefing(cyclone)}${lastForecast ? ` The model forecast reaches ${lastForecast.windKmh} km/h by ${lastForecast.label}.` : " No forecast is available for it."}`
          : "No storm is selected."}</p>
        {cyclone && <div className="briefing-footer"><span>Wind now <b>{formatWind(cyclone.windKmh, preferences.windUnit)}</b></span><span>Pressure <b>{formatPressure(cyclone.pressureHpa, preferences.pressureUnit)}</b></span></div>}
      </Panel>
    </div>
  </div>;
}
