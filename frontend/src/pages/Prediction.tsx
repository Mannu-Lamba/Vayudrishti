import { BrainCircuit, FlaskConical, MapPinned, Radio, Satellite as SatelliteIcon } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ApiErrorState from "@/components/common/ApiErrorState";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import LoadingBlock from "@/components/common/LoadingBlock";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import ForecastCharts from "@/components/charts/ForecastCharts";
import CycloneMap from "@/components/map/CycloneMap";
import ConfidencePanel from "@/components/prediction/ConfidencePanel";
import CurrentCycloneSummary from "@/components/prediction/CurrentCycloneSummary";
import ImageAnalysisPanel from "@/components/prediction/ImageAnalysisPanel";
import ModelForecastPanel from "@/components/prediction/ModelForecastPanel";
import ForecastDetailPanel from "@/components/prediction/ForecastDetailPanel";
import ModelInfoPanel from "@/components/prediction/ModelInfoPanel";
import ModelStatusPanel from "@/components/prediction/ModelStatusPanel";
import PredictionSelector from "@/components/prediction/PredictionSelector";
import PredictionSummaryCards from "@/components/prediction/PredictionSummaryCards";
import PredictionTimeline from "@/components/prediction/PredictionTimeline";
import UncertaintyPanel from "@/components/prediction/UncertaintyPanel";
import { useApiStatus } from "@/hooks/useApiStatus";
import { useCycloneMapData } from "@/hooks/useCycloneMap";
import { useCyclones } from "@/hooks/useCyclones";
import { useMlAssessment, useModelRegistry, usePrediction } from "@/hooks/usePrediction";
import { useRegions } from "@/hooks/useRegions";
import { forecastLabelFor, mapStatusFor, toMapMarkers } from "@/lib/mapScene";
import { describeSelection, resolveCycloneArea, resolveSelection, sectorsFor, summarizeRegions } from "@/lib/regions";
import { routeTo } from "@/lib/routes";
import { useSearchParamState } from "@/lib/searchParams";

// State in the URL: ?region, subregion, cyclone (id or code, e.g. VD-001), h (selected horizon).
export default function Prediction() {
  const navigate = useNavigate();
  const [params, updateParams] = useSearchParamState();
  const api = useApiStatus();

  const regionsQuery = useRegions();
  const regions = useMemo(() => regionsQuery.data ?? [], [regionsQuery.data]);
  const allQuery = useCyclones();
  const allCyclones = useMemo(() => allQuery.data ?? [], [allQuery.data]);

  // /prediction?cyclone=VD-001 without a region opens in that cyclone's own region/subregion.
  const requested = params.get("cyclone")?.toLowerCase();
  const requestedCyclone = allCyclones.find((cyclone) => cyclone.id === requested || cyclone.code.toLowerCase() === requested);
  const selection = !params.get("region") && requestedCyclone
    ? resolveCycloneArea(regions, requestedCyclone) ?? resolveSelection(regions, null, null)
    : resolveSelection(regions, params.get("region"), params.get("subregion"));
  const details = describeSelection(regions, selection);
  const summaries = useMemo(() => summarizeRegions(regions, allCyclones), [regions, allCyclones]);

  const regionalQuery = useCyclones(selection);
  const cyclones = useMemo(() => regionalQuery.data ?? [], [regionalQuery.data]);
  const cyclone = cyclones.find((candidate) => candidate.id === requestedCyclone?.id) ?? cyclones[0] ?? null;
  const cycloneId = cyclone?.id;

  const prediction = usePrediction(cycloneId);
  // Observed track + this prediction's forecast. No prediction → the map shows the observed track only.
  const mapData = useCycloneMapData(cycloneId);
  const assessment = useMlAssessment(cycloneId);
  const models = useModelRegistry();

  const forecast = prediction.data?.forecast ?? [];
  const lastHours = forecast[forecast.length - 1]?.hours ?? 0;
  const requestedHours = Number(params.get("h"));
  const selectedHours = params.get("h") != null && (requestedHours === 0 || forecast.some((point) => point.hours === requestedHours)) ? requestedHours : lastHours;
  const selectedPoint = forecast.find((point) => point.hours === selectedHours) ?? null;

  const predictionData = prediction.data;
  const markers = useMemo(() => toMapMarkers(cyclones), [cyclones]);
  const sectors = useMemo(() => sectorsFor(details.region, selection.subregionId), [details.region, selection.subregionId]);

  const context = { region: selection.regionId, subregion: selection.subregionId, cyclone: cycloneId };
  const changeRegion = (regionId: string) => updateParams({ region: regionId, subregion: null, cyclone: null, h: null });
  const changeSubregion = (subregionId: string | undefined) => updateParams({ region: selection.regionId, subregion: subregionId ?? null, cyclone: null, h: null });
  const changeCyclone = (id: string) => updateParams({ region: selection.regionId, subregion: selection.subregionId ?? null, cyclone: id, h: null });
  const selectHours = (hours: number) => updateParams({ region: selection.regionId, subregion: selection.subregionId ?? null, cyclone: cycloneId, h: String(hours) });
  const selectForecastPoint = (id: string) => {
    const point = forecast.find((candidate) => candidate.id === id);
    if (point) selectHours(point.hours);
  };

  const modelOutputLabel = forecastLabelFor(prediction.source);
  const predictionPanel = prediction.loading
    ? <Panel eyebrow="AI PREDICTION SUMMARY" title="Loading prediction"><div className="panel-body"><LoadingBlock label="LOADING PREDICTION" rows={4} /></div></Panel>
    : prediction.error
      ? <Panel eyebrow="AI PREDICTION SUMMARY" title="Prediction unavailable"><div className="panel-body"><ApiErrorState error={prediction.error} onRetry={prediction.refetch} subject="the prediction" /></div></Panel>
      : !predictionData
        ? <Panel eyebrow="AI PREDICTION SUMMARY" title="No prediction" data-testid="prediction-empty"><div className="panel-body"><StateNotice variant="empty" title="NO PREDICTION AVAILABLE" message="The selected cyclone does not currently have a prediction result." /></div></Panel>
        : <PredictionSummaryCards prediction={predictionData} selected={selectedPoint} source={prediction.source} classificationConfidence={assessment.data?.classification?.confidence} />;

  return (
    <div className="page-stack" data-testid="prediction-page">
      <div className="page-intro-row">
        <div>
          <div className="section-kicker"><BrainCircuit size={13} /> AI PREDICTION CENTER</div>
          <h2 className="page-heading">AI prediction</h2>
          <p className="page-subheading">Track, intensity and uncertainty outlook for the selected system — {details.region ? details.path : "region data unavailable"}.</p>
        </div>
        <div className="page-intro-actions">
          <button type="button" className="secondary-action" onClick={() => navigate(routeTo.satellite(context))} data-testid="prediction-open-satellite"><SatelliteIcon size={14} /> SATELLITE VIEW</button>
          <button type="button" className="primary-action" onClick={() => navigate(routeTo.cyclones(context))} data-testid="prediction-view-on-map"><MapPinned size={14} /> VIEW ON MAP</button>
        </div>
      </div>

      <div className={`pred-mode-banner ${api.isDemo ? "pred-mode-demo" : "pred-mode-live"}`} data-testid="prediction-mode-banner">
        {api.isDemo ? <FlaskConical size={15} /> : <Radio size={15} />}
        <strong>{api.isDemo ? "USING DEMO PREDICTION" : "LIVE MODEL OUTPUT"}</strong>
        <span>{api.isDemo ? "Illustrative values for interface design — no ML model is running yet." : "Forecasts come from the connected VayuDrishti inference service."}</span>
      </div>

      {regionsQuery.error ? <ApiErrorState error={regionsQuery.error} onRetry={regionsQuery.refetch} subject="regions" /> : null}

      <PredictionSelector
        regions={regions}
        region={details.region}
        selection={selection}
        summaries={summaries}
        cyclones={cyclones}
        cycloneId={cycloneId}
        onRegionChange={changeRegion}
        onSubregionChange={changeSubregion}
        onCycloneChange={changeCyclone}
      />

      {regionalQuery.loading || regionsQuery.loading ? (
        <Panel><div className="panel-body"><LoadingBlock label="LOADING CYCLONE DATA" /></div></Panel>
      ) : regionalQuery.error ? (
        <ApiErrorState error={regionalQuery.error} onRetry={regionalQuery.refetch} subject="cyclone data" />
      ) : !cyclone ? (
        <StateNotice variant="no-systems" message={`No active tropical cyclones in the ${details.label}.${details.season ? ` Season: ${details.season}.` : ""}`} />
      ) : (
        <>
          <div className="pred-top-grid">
            <CurrentCycloneSummary cyclone={cyclone} source={regionalQuery.source} />
            {predictionPanel}
          </div>

          {predictionData && <PredictionTimeline current={predictionData.current} forecast={forecast} selectedHours={selectedHours} onSelect={selectHours} />}

          <div className="pred-main-grid">
            <CycloneMap
              cyclones={markers}
              selectedCycloneId={cycloneId}
              onCycloneSelect={changeCyclone}
              scene={mapData.scene}
              dataSource={prediction.source}
              districts={mapData.districts}
              status={mapStatusFor(undefined, mapData)}
              selectedForecastId={selectedPoint?.id}
              onForecastSelect={selectForecastPoint}
              forecastLabel={modelOutputLabel}
              variant="full"
              showTimeline={false}
              viewport={details.viewport}
              eyebrow={`PREDICTED TRACK / ${cyclone.code}`}
              title="Prediction map"
              tags={details.landmarks.slice(0, 3).map((landmark) => landmark.label)}
              sectors={sectors}
            />
            <div className="pred-side-stack">
              {predictionData ? (
                <>
                  <ForecastDetailPanel point={selectedPoint} current={predictionData.current} source={prediction.source} />
                  <ConfidencePanel confidence={predictionData.confidence} assessment={assessment.data} source={prediction.source} />
                  <UncertaintyPanel prediction={predictionData} selectedHours={selectedHours} onSelect={selectHours} source={prediction.source} />
                </>
              ) : !prediction.loading && !prediction.error && (
                <StateNotice variant="empty" title="NO FORECAST AVAILABLE" message="The map shows the observed track only." />
              )}
            </div>
          </div>

          <ForecastCharts prediction={predictionData} source={prediction.source} loading={prediction.loading} expanded selectedHours={selectedHours} />
        </>
      )}

      <ModelForecastPanel />

      <ImageAnalysisPanel />

      <div className="pred-bottom-grid">
        {models.error
          ? <Panel eyebrow="MODEL STATUS" title="Pipeline readiness"><div className="panel-body"><ApiErrorState error={models.error} onRetry={models.refetch} subject="model status" /></div></Panel>
          : <ModelStatusPanel components={models.data?.components ?? []} apiStatus={api.status} source={models.source} />}
        {models.data && <ModelInfoPanel models={models.data.models} task="track" predictionVersion={predictionData?.modelVersion} source={models.source} />}
      </div>

      <div className="pred-footnote">Data source for this page: <DataSourceBadge source={prediction.source ?? models.source} variant="model" /></div>
    </div>
  );
}
