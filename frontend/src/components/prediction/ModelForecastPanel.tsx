import { AlertTriangle, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import ApiErrorState from "@/components/common/ApiErrorState";
import LoadingBlock from "@/components/common/LoadingBlock";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import ForecastCharts from "@/components/charts/ForecastCharts";
import CycloneMap from "@/components/map/CycloneMap";
import ForecastDetailPanel from "@/components/prediction/ForecastDetailPanel";
import PredictionTimeline from "@/components/prediction/PredictionTimeline";
import UncertaintyPanel from "@/components/prediction/UncertaintyPanel";
import { MAP_VIEWPORTS } from "@/config/mapViewports";
import { useObservedTrack, usePredictionCases, usePredictionServiceStatus, useRunPrediction } from "@/hooks/usePrediction";
import { formatCoordsCompact, haversineKm } from "@/lib/geo";
import { formatFixTime, sceneFromPrediction } from "@/lib/mapScene";
import { ApiError, describeApiError, type ApiErrorCopy } from "@/services/apiClient";
import { normalizeTrack } from "@/services/cycloneApi";
import type { PredictionServiceState } from "@/services/predictionApi";
import type { MlErrorBody, PredictionCase, PredictionRequest } from "@/types/model";
import type { MapCycloneMarker } from "@/types/track";

// The trained track model on a held-out storm: pick a storm and a forecast time, run the model
// (POST /api/ml/predict) and see its T+6…24 h track, wind and pressure — and what the storm actually did.
// Always the real backend, in demo mode too: a forecast can only come from the model, so there is no
// mock here and nothing is shown when the backend, the model or the history is missing.

const ANCHOR = "track-forecast";
const KT_PER_KMH = 1 / 1.852;
const AREA_LABELS: Record<string, string> = {
  bay_of_bengal: "Bay of Bengal",
  arabian_sea: "Arabian Sea",
  south_indian_ocean: "South Indian Ocean",
  western_pacific: "Western Pacific",
  eastern_pacific: "Eastern Pacific",
  southern_pacific: "Southern Pacific",
};
/** Backend codes that mean "no forecast for this time" (an empty state, not a failure). */
const NOT_AVAILABLE_CODES = new Set(["INSUFFICIENT_HISTORY", "MISSING_CURRENT_INTENSITY", "OBSERVATION_NOT_FOUND"]);

/** Badge: the backend/model state from GET /api/health + /api/ml/status, or PREDICTION RUNNING during a run. */
type BadgeState = PredictionServiceState | "checking" | "running";
const BADGE: Record<BadgeState, { label: string; tone: string }> = {
  checking: { label: "CHECKING MODEL", tone: "muted" },
  backend_unavailable: { label: "BACKEND UNAVAILABLE", tone: "red" },
  loading: { label: "MODEL LOADING", tone: "cyan" },
  ready: { label: "MODEL READY", tone: "green" },
  unavailable: { label: "MODEL UNAVAILABLE", tone: "muted" },
  error: { label: "MODEL ERROR", tone: "red" },
  running: { label: "PREDICTION RUNNING", tone: "cyan" },
};

const MODEL_NOTICE: Record<"loading" | "unavailable" | "error", { title: string; message: string }> = {
  loading: { title: "MODEL LOADING", message: "The prediction model is loading on the backend. Run prediction becomes available when it is ready." },
  unavailable: { title: "MODEL UNAVAILABLE", message: "Prediction model is currently unavailable." },
  error: { title: "MODEL ERROR", message: "The prediction model failed to load on the backend, so no forecast can be run." },
};

/** One run of POST /api/ml/predict for the current selection. */
type RunState = "idle" | "loading" | "success" | "error" | "model_unavailable" | "insufficient_data";

const displayName = (name: string) =>
  name === "NOT_NAMED" ? "Unnamed" : name.split(/([:\-\s])/).map((part) => part.charAt(0) + part.slice(1).toLowerCase()).join("");
const caseLabel = (c: PredictionCase) => `${displayName(c.name)} (${c.season}) · peak ${c.peakWindKt ?? "—"} kt`;

function mlError(error: unknown) {
  return error instanceof ApiError && error.kind === "http" ? (error.body as Partial<MlErrorBody> | null)?.error ?? null : null;
}

/** The backend's own message when it sent one (never a stack trace), otherwise generic operator wording. */
function errorCopy(error: unknown): ApiErrorCopy {
  const body = mlError(error);
  if (body?.message && error instanceof ApiError) {
    return { title: error.status === 503 ? "SERVICE UNAVAILABLE" : error.status >= 500 ? "PREDICTION FAILED" : "REQUEST NOT ACCEPTED", message: body.message };
  }
  return describeApiError(error);
}

function StatusBadge({ state }: { state: BadgeState }) {
  const meta = BADGE[state];
  return (
    <span className={`model-status-badge model-status-${meta.tone}`} data-testid="model-forecast-status" data-state={state}>
      <span className="model-status-dot" />{meta.label}
    </span>
  );
}

export default function ModelForecastPanel() {
  const status = usePredictionServiceStatus();
  const casesQuery = usePredictionCases();
  const run = useRunPrediction();
  const cases = useMemo(() => casesQuery.data?.cases ?? [], [casesQuery.data]);
  const areas = useMemo(() => Object.keys(AREA_LABELS).filter((id) => cases.some((c) => c.area === id && c.forecastOrigins.length)), [cases]);

  const [area, setArea] = useState("bay_of_bengal");
  const [cycloneId, setCycloneId] = useState<string>();
  const [at, setAt] = useState<string>();
  const [hours, setHours] = useState(24);

  const activeArea = areas.includes(area) ? area : areas[0];
  const areaCases = useMemo(
    () => cases.filter((c) => c.area === activeArea && c.forecastOrigins.length).sort((a, b) => (b.peakWindKt ?? 0) - (a.peakWindKt ?? 0)),
    [cases, activeArea],
  );
  const selectedCase = areaCases.find((c) => c.cycloneId === cycloneId) ?? areaCases[0];
  const origins = useMemo(() => selectedCase?.forecastOrigins ?? [], [selectedCase]);
  const activeAt = at ?? origins[Math.floor(origins.length / 2)];

  const trackQuery = useObservedTrack(selectedCase?.cycloneId);
  const points = useMemo(() => trackQuery.data?.points ?? [], [trackQuery.data]);

  useEffect(() => {
    if (window.location.hash === `#${ANCHOR}`) document.getElementById(ANCHOR)?.scrollIntoView({ block: "start" });
  }, []);

  const originSet = useMemo(() => new Set(origins), [origins]);
  const timeOptions = useMemo(() => {
    const all = points.length ? points.map((point) => point.timestamp) : origins;
    return activeAt && !all.includes(activeAt) ? [...all, activeAt].sort() : all;
  }, [points, origins, activeAt]);

  // ── Backend / model state (GET /api/health + GET /api/ml/status) ──
  const serviceState = status.data?.state;
  const modelReady = serviceState === "ready";

  // ── The run for the current selection (a result for another storm or time is never shown) ──
  const forSelection = run.variables?.cycloneId === selectedCase?.cycloneId && run.variables?.timestamp === activeAt;
  const runErrorInfo = forSelection ? mlError(run.error) : null;
  const runState: RunState = !forSelection || run.isIdle ? "idle"
    : run.isPending ? "loading"
      : run.isSuccess ? "success"
        : runErrorInfo?.code === "MODEL_NOT_LOADED" ? "model_unavailable"
          : runErrorInfo && NOT_AVAILABLE_CODES.has(runErrorInfo.code) ? "insufficient_data"
            : "error";
  const result = runState === "success" ? run.data : undefined;
  const prediction = result?.prediction ?? null;
  const response = result?.response;
  const badge: BadgeState = runState === "loading" ? "running" : serviceState ?? "checking";

  const runPrediction = () => {
    if (!selectedCase || !activeAt) return;
    const fix = points.find((point) => point.timestamp === activeAt);
    const payload: PredictionRequest = {
      cycloneId: selectedCase.cycloneId,
      timestamp: activeAt,
      ...(fix ? { latitude: fix.latitude, longitude: fix.longitude } : {}),
    };
    run.mutate(payload, { onError: (error) => { if (mlError(error)?.code === "MODEL_NOT_LOADED") status.refetch(); } });
  };
  const recheck = () => { status.refetch(); casesQuery.refetch(); };

  const horizons = prediction?.forecast.map((point) => point.hours) ?? [];
  const selectedHours = hours === 0 || horizons.includes(hours) ? hours : horizons[horizons.length - 1] ?? 0;
  const selectedPoint = prediction?.forecast.find((point) => point.hours === selectedHours) ?? null;

  // Observed fixes up to the forecast time only: the map shows what the model knew.
  const scene = useMemo(() => {
    if (!prediction || !selectedCase) return null;
    const t0 = Date.parse(prediction.issuedAt);
    const history = points.filter((point) => Date.parse(point.timestamp) <= t0);
    const track = history.length ? normalizeTrack({ cycloneId: selectedCase.cycloneId, observedAt: prediction.issuedAt, points: history }) : null;
    return sceneFromPrediction(prediction, track);
  }, [prediction, points, selectedCase]);

  const markers = useMemo<MapCycloneMarker[]>(() => (prediction && selectedCase ? [{
    id: selectedCase.cycloneId,
    code: displayName(selectedCase.name),
    name: displayName(selectedCase.name),
    category: prediction.current.category,
    status: "active",
    latitude: prediction.current.latitude,
    longitude: prediction.current.longitude,
    windKmh: prediction.current.windKmh,
    pressureHpa: prediction.current.pressureHpa,
    observedAt: formatFixTime(prediction.current.observedAt),
  }] : []), [prediction, selectedCase]);

  // The storm is held out: its later fixes verify the forecast (they were never used for training).
  const verification = useMemo(() => (prediction ? prediction.forecast.map((point) => {
    const observed = points.find((candidate) => candidate.timestamp === point.forecastTime);
    return { point, observed, errorKm: observed ? haversineKm(point, observed) : null };
  }) : []), [prediction, points]);

  const changeArea = (id: string) => { setArea(id); setCycloneId(undefined); setAt(undefined); };
  const changeCyclone = (id: string) => { setCycloneId(id); setAt(undefined); };
  const selectForecast = (id: string) => {
    const point = prediction?.forecast.find((candidate) => candidate.id === id);
    if (point) setHours(point.hours);
  };

  let body: ReactNode = null;
  if (serviceState === "backend_unavailable") {
    body = (
      <div className="panel-body" data-testid="model-forecast-backend-unavailable">
        <StateNotice variant="offline" title="BACKEND UNAVAILABLE" message="Unable to connect to the VayuDrishti API, so the prediction model cannot be reached."
          action={<button type="button" className="secondary-action mf-retry" onClick={recheck}><RefreshCw size={13} /> Retry</button>} />
      </div>
    );
  } else if (casesQuery.loading) body = <div className="panel-body"><LoadingBlock label="LOADING HELD-OUT STORMS" rows={2} /></div>;
  else if (casesQuery.error) body = <div className="panel-body"><ApiErrorState error={casesQuery.error} onRetry={recheck} {...errorCopy(casesQuery.error)} /></div>;
  else if (serviceState && serviceState !== "ready" && runState !== "success") {
    const notice = MODEL_NOTICE[serviceState];
    const detail = status.data?.model?.message;
    body = (
      <div className="panel-body" data-testid="model-forecast-model-state" data-state={serviceState}>
        <StateNotice variant="unavailable" title={notice.title} message={detail ? `${notice.message} ${detail}` : notice.message} />
      </div>
    );
  } else if (runState === "loading") body = <div className="panel-body"><LoadingBlock label="PREDICTION RUNNING" rows={2} /></div>;
  else if (runState === "model_unavailable") {
    body = <div className="panel-body" data-testid="model-forecast-model-state" data-state="unavailable"><StateNotice variant="unavailable" title="MODEL UNAVAILABLE" message="Prediction model is currently unavailable." /></div>;
  } else if (runState === "insufficient_data" && runErrorInfo) {
    body = (
      <div className="panel-body" data-testid="model-forecast-not-available" data-code={runErrorInfo.code}>
        <StateNotice variant="empty" title="PREDICTION NOT AVAILABLE"
          message={runErrorInfo.code === "INSUFFICIENT_HISTORY" ? "Prediction unavailable: insufficient historical observations for the selected cyclone." : runErrorInfo.message} />
      </div>
    );
  } else if (runState === "error") {
    const retry = run.error instanceof ApiError && run.error.retryable ? runPrediction : undefined;
    body = <div className="panel-body" data-testid="model-forecast-error"><ApiErrorState error={run.error} onRetry={retry} {...errorCopy(run.error)} /></div>;
  } else if (runState === "success" && response && prediction) {
    const input = response.input;
    body = (
      <>
        <dl className="pred-facts mf-facts" data-testid="model-forecast-meta">
          <div><dt>Forecast time (T0)</dt><dd className="mf-mono">{formatFixTime(prediction.issuedAt)}</dd></div>
          <div><dt>Input</dt><dd>{input ? `${input.observationsUsed} fixes · last ${input.historyWindowHours} h, every ${input.observationIntervalHours} h` : "—"}</dd></div>
          <div><dt>Model</dt><dd>{response.model ? `${response.model.displayName} ${response.model.version} · ${response.model.architecture.toUpperCase()}` : response.modelVersion}</dd></div>
          <div><dt>Observed at T0</dt><dd>{prediction.current.category} · {Math.round(prediction.current.windKmh * KT_PER_KMH)} kt · {prediction.current.pressureHpa} hPa</dd></div>
          <div><dt>Confidence</dt><dd>Not produced by the model — see the uncertainty radius</dd></div>
          <div><dt>Generated</dt><dd className="mf-mono">{response.generatedAt ? formatFixTime(response.generatedAt) : "—"}{response.cached ? " · cached" : ""}</dd></div>
        </dl>
        {response.disclaimer && <p className="mf-disclaimer"><AlertTriangle size={13} />{response.disclaimer}</p>}
      </>
    );
  } else if (selectedCase) {
    body = (
      <p className="mf-idle" data-testid="model-forecast-idle">
        Choose a cyclone and a forecast time, then run the prediction. The trained model on the backend computes it from the storm's
        last 24 h of observations.
      </p>
    );
  }

  const canRun = modelReady && Boolean(selectedCase && activeAt) && runState !== "loading";

  return (
    <section className="mf-section" id={ANCHOR} data-testid="model-forecast-section">
      <Panel eyebrow="TRACK FORECAST · TRAINED MODEL" title="Forecast a held-out cyclone" action={<StatusBadge state={badge} />} data-testid="model-forecast-panel">
        <div className="mf-controls">
          <label>
            <span>Area</span>
            <select className="vd-select" value={activeArea ?? ""} onChange={(event) => changeArea(event.target.value)} disabled={!areas.length} data-testid="model-forecast-area">
              {areas.map((id) => <option key={id} value={id}>{AREA_LABELS[id]}</option>)}
            </select>
          </label>
          <label>
            <span>Cyclone (test storm)</span>
            <select className="vd-select" value={selectedCase?.cycloneId ?? ""} onChange={(event) => changeCyclone(event.target.value)} disabled={!areaCases.length} data-testid="model-forecast-cyclone">
              {areaCases.map((c) => <option key={c.cycloneId} value={c.cycloneId}>{caseLabel(c)}</option>)}
            </select>
          </label>
          <label>
            <span>Forecast time (T0)</span>
            <select className="vd-select" value={activeAt ?? ""} onChange={(event) => setAt(event.target.value)} disabled={!timeOptions.length} data-testid="model-forecast-time">
              {timeOptions.map((ts) => <option key={ts} value={ts}>{formatFixTime(ts)}{originSet.has(ts) ? "" : " · no forecast"}</option>)}
            </select>
          </label>
          <button type="button" className="primary-action mf-run" onClick={runPrediction} disabled={!canRun} data-testid="model-forecast-run">
            {runState === "loading" ? <><LoaderCircle size={14} className="state-spinner" /> Prediction running…</> : <><Play size={14} /> Run prediction</>}
          </button>
        </div>
        {body}
        {casesQuery.data?.note && <p className="mf-note">{casesQuery.data.note}</p>}
      </Panel>

      {prediction && scene && selectedCase && (
        <>
          <PredictionTimeline current={prediction.current} forecast={prediction.forecast} selectedHours={selectedHours} onSelect={setHours} />
          <div className="pred-main-grid">
            <CycloneMap
              cyclones={markers}
              selectedCycloneId={selectedCase.cycloneId}
              scene={scene}
              dataSource="live"
              selectedForecastId={selectedPoint?.id}
              onForecastSelect={selectForecast}
              forecastLabel="LIVE MODEL OUTPUT · HELD-OUT STORM"
              variant="full"
              showTimeline={false}
              viewport={MAP_VIEWPORTS[selectedCase.area]}
              eyebrow={`MODEL FORECAST / ${displayName(selectedCase.name).toUpperCase()} ${selectedCase.season}`}
              title="Forecast track"
              tags={[AREA_LABELS[selectedCase.area] ?? selectedCase.area, `T0 ${formatFixTime(prediction.issuedAt)}`]}
            />
            <div className="pred-side-stack">
              <ForecastDetailPanel point={selectedPoint} current={prediction.current} source="live" />
              <UncertaintyPanel prediction={prediction} selectedHours={selectedHours} onSelect={setHours} source="live" />
            </div>
          </div>
          <ForecastCharts prediction={prediction} source="live" expanded selectedHours={selectedHours} />
          <Panel eyebrow="VERIFICATION · HELD-OUT STORM" title="Forecast vs what happened" data-testid="model-forecast-verification">
            <div className="mf-verify-wrap">
              <table className="mf-verify">
                <thead>
                  <tr><th>Lead</th><th>Forecast position</th><th>Observed position</th><th>Track error</th><th>Forecast wind</th><th>Observed wind</th><th>Within radius</th></tr>
                </thead>
                <tbody>
                  {verification.map(({ point, observed, errorKm }) => (
                    <tr key={point.id} className={point.hours === selectedHours ? "mf-row-active" : ""} data-testid={`verification-${point.hours}`}>
                      <td>{point.label}</td>
                      <td className="mf-mono">{formatCoordsCompact(point.latitude, point.longitude)}</td>
                      <td className="mf-mono">{observed ? formatCoordsCompact(observed.latitude, observed.longitude) : "Not observed"}</td>
                      <td>{errorKm == null ? "—" : `${Math.round(errorKm)} km`}</td>
                      <td>{Math.round(point.windKmh * KT_PER_KMH)} kt</td>
                      <td>{observed && typeof observed.windKmh === "number" ? `${Math.round(observed.windKmh * KT_PER_KMH)} kt` : "—"}</td>
                      <td>{errorKm == null || !point.uncertaintyRadiusKm ? "—" : errorKm <= point.uncertaintyRadiusKm ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel-note">This storm was held out of training and validation. Its later fixes are used here only to check the forecast.</div>
          </Panel>
        </>
      )}
    </section>
  );
}
