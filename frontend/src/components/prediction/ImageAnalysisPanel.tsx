import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, RotateCcw, ScanSearch, Upload } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent } from "react";
import Panel from "@/components/common/Panel";
import { useModelRegistry } from "@/hooks/usePrediction";
import { formatCoordsCompact } from "@/lib/geo";
import { formatFixTime } from "@/lib/mapScene";
import { ApiError, describeApiError, type ApiErrorCopy } from "@/services/apiClient";
import { analyzeImage } from "@/services/predictionApi";
import type { AnalysisPrediction, ImageAnalysisResponse, MlErrorBody, PredictionModelStatus } from "@/types/model";

// Drop an IR satellite image → POST /api/ml/analyze → identification, classification when a cyclone
// is found, and a track forecast when a storm ID is given and its observation history allows one.
// Always the real backend models: there is no demo/mock result for an upload.

const MODEL_BADGE: Record<string, { label: string; tone: string }> = {
  ready: { label: "MODEL READY", tone: "green" },
  loading: { label: "MODEL LOADING", tone: "cyan" },
  unavailable: { label: "MODEL UNAVAILABLE", tone: "muted" },
  error: { label: "MODEL ERROR", tone: "red" },
};
const NO_FORECAST_TITLE: Record<string, string> = {
  NO_CYCLONE_DETECTED: "NOT RUN",
  STORM_ID_REQUIRED: "NEEDS A STORM ID",
  INSUFFICIENT_HISTORY: "INSUFFICIENT DATA",
  MISSING_FEATURES: "INSUFFICIENT DATA",
  MISSING_CURRENT_INTENSITY: "INSUFFICIENT DATA",
  MODEL_NOT_LOADED: "MODEL UNAVAILABLE",
};

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;
const IDENTIFY_ANCHOR = "identify-cyclone";

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

function errorCopy(error: unknown): ApiErrorCopy {
  if (error instanceof ApiError && error.kind === "http") {
    const message = (error.body as Partial<MlErrorBody> | null)?.error?.message;
    if (message) {
      const title = error.status === 503 ? "MODEL NOT AVAILABLE" : error.status === 502 ? "BACKEND UNAVAILABLE" : error.status >= 500 ? "ANALYSIS FAILED" : "IMAGE NOT ACCEPTED";
      return { title, message };
    }
  }
  return describeApiError(error);
}

function ErrorNotice({ copy, onRetry }: { copy: ApiErrorCopy; onRetry?: () => void }) {
  return (
    <div className="api-error-state" role="alert" data-testid="image-analysis-error">
      <AlertTriangle size={18} />
      <div>
        <strong>{copy.title}</strong>
        <span>{copy.message}</span>
        {onRetry && (
          <div className="api-error-actions">
            <button type="button" className="secondary-action" onClick={onRetry}><RotateCcw size={13} />Retry</button>
          </div>
        )}
      </div>
    </div>
  );
}

function ProbabilityBar({ label, value, active = false }: { label: string; value: number; active?: boolean }) {
  return (
    <div className={`ia-bar ${active ? "ia-bar-active" : ""}`}>
      <div className="ia-bar-head"><span>{label}</span><span>{percent(value)}</span></div>
      <div className="ia-bar-track"><div className="ia-bar-fill" style={{ width: percent(value) }} /></div>
    </div>
  );
}

/** The forecast stage spans the whole result grid (below identification + classification) so its table is not clipped. */
const FULL_ROW = { gridColumn: "1 / -1" } as const;

/** Stage 3: the model's forecast from the storm's history, or why there is none — straight from the backend. */
function ForecastStage({ prediction }: { prediction: AnalysisPrediction }) {
  const forecast = prediction.available ? prediction.forecast : null;
  if (!forecast) {
    return (
      <div className="ia-classification" style={FULL_ROW} data-testid="analysis-forecast" data-available="false" data-reason={prediction.reason ?? ""}>
        <small>Track forecast</small>
        <strong>{NO_FORECAST_TITLE[prediction.reason ?? ""] ?? "NOT AVAILABLE"}</strong>
        <p className="ia-skipped">{prediction.message ?? "No forecast was produced."}</p>
      </div>
    );
  }
  return (
    <div className="ia-classification" style={FULL_ROW} data-testid="analysis-forecast" data-available="true">
      <small>Track forecast · {forecast.name || forecast.cycloneId} · T0 {forecast.issuedAt ? formatFixTime(forecast.issuedAt) : "—"}</small>
      <div className="mf-verify-wrap">
        <table className="mf-verify">
          <thead><tr><th>Lead</th><th>Position</th><th>Wind</th><th>Pressure</th><th>Radius</th></tr></thead>
          <tbody>
            {forecast.forecast.map((step) => (
              <tr key={step.hours} data-testid={`analysis-forecast-${step.hours}`}>
                <td>T+{step.hours}h</td>
                <td className="mf-mono">{formatCoordsCompact(step.latitude, step.longitude)}</td>
                <td>{step.windSpeedKt != null ? `${Math.round(step.windSpeedKt)} kt` : `${Math.round(step.windSpeed)} km/h`}</td>
                <td>{Math.round(step.pressure)} hPa</td>
                <td>{step.uncertaintyRadiusKm ? `±${Math.round(step.uncertaintyRadiusKm)} km` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ia-skipped">Confidence is not produced by the model; the radius is its empirical 67 % error. See Track forecast for the map.</p>
    </div>
  );
}

function AnalysisResult({ result }: { result: ImageAnalysisResponse }) {
  const { identification, classification } = result;
  return (
    <div className="image-analysis-result" data-testid="image-analysis-result">
      <div className={`ia-verdict ${identification.detected ? "ia-verdict-cyclone" : "ia-verdict-clear"}`}>
        <small>Identification</small>
        <strong data-testid="identification-label">{identification.detected ? "CYCLONE" : "NO CYCLONE"}</strong>
        <span data-testid="identification-confidence">Confidence {percent(identification.confidence)}</span>
        <ProbabilityBar label="Cyclone probability" value={identification.cyclone_probability} active />
      </div>
      <div className="ia-classification">
        <small>Intensity (IMD scale)</small>
        {classification ? (
          <div data-testid="classification-result">
            <strong data-testid="classification-label">{classification.class_name}</strong>
            <span className="ia-class-meta">{classification.class_code} · confidence {percent(classification.confidence)}</span>
            <ul className="ia-probabilities">
              {Object.entries(classification.probabilities).map(([name, value]) => (
                <li key={name}><ProbabilityBar label={name} value={value} active={name === classification.class_name} /></li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="ia-skipped" data-testid="classification-skipped">{result.classification_skipped_reason ?? "Classification was not run."}</p>
        )}
      </div>
      <ForecastStage prediction={result.prediction} />
      <div className="ia-foot">
        <span>
          {Object.values(result.models).map((model) => `${model.name} ${model.version}`).join(" · ")} · {Math.round(result.inference.processing_time_ms)} ms
        </span>
        <span>Confidence is the model&apos;s softmax score, not a calibrated probability.</span>
      </div>
    </div>
  );
}

function ModelBadge({ model, running }: { model?: PredictionModelStatus; running: boolean }) {
  const meta = running ? { label: "INFERENCE RUNNING", tone: "cyan" } : MODEL_BADGE[model?.status ?? ""] ?? { label: "MODEL STATUS UNKNOWN", tone: "muted" };
  return (
    <span className={`model-status-badge model-status-${meta.tone}`} data-testid="image-analysis-status" data-state={running ? "running" : model?.status ?? "unknown"}
      title={model?.message ?? undefined}>
      <span className="model-status-dot" />{meta.label}
    </span>
  );
}

export default function ImageAnalysisPanel() {
  const inputId = useId();
  const previewUrl = useRef<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [stormId, setStormId] = useState("");
  const [imageTime, setImageTime] = useState("");
  const registry = useModelRegistry();
  // Optional storm context enables stage 3 (track forecast from the storm's history); the time is read as UTC.
  const analysis = useMutation({
    mutationFn: (image: File) => analyzeImage(image, { storm_id: stormId.trim() || null, timestamp: imageTime ? `${imageTime}:00Z` : null }),
  });

  useEffect(() => {
    if (window.location.hash === `#${IDENTIFY_ANCHOR}`) document.getElementById(IDENTIFY_ANCHOR)?.scrollIntoView({ block: "start" });
    return () => {
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    };
  }, []);

  function choose(next: File | undefined) {
    if (!next) return;
    analysis.reset();
    setLocalError(null);
    if (next.size > MAX_BYTES) return setLocalError("The image is larger than 10 MB.");
    if (next.type && !ACCEPTED_TYPES.includes(next.type)) return setLocalError("Choose a PNG, JPEG, TIFF, BMP or WebP image.");
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(next);
    setPreview(previewUrl.current);
    setFile(next);
    analysis.mutate(next);
  }

  function reset() {
    analysis.reset();
    setLocalError(null);
    setFile(null);
    setPreview(null);
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files?.[0]);
  };

  return (
    <Panel
      id={IDENTIFY_ANCHOR}
      eyebrow="IMAGE ANALYSIS · LIVE MODEL"
      title="Identify cyclone"
      className="image-analysis-panel"
      data-testid="image-analysis-panel"
      action={(
        <>
          <ModelBadge model={registry.data?.identification} running={analysis.isPending} />
          {file && <button type="button" className="secondary-action" onClick={() => analysis.mutate(file)} disabled={analysis.isPending} data-testid="image-analysis-rerun">Analyse again</button>}
          {file && <button type="button" className="secondary-action" onClick={reset} data-testid="image-analysis-reset">New image</button>}
        </>
      )}
    >
      <div className="mf-controls">
        <label>
          <span>Storm ID (optional, enables the track forecast)</span>
          <input className="vd-select" value={stormId} onChange={(event) => setStormId(event.target.value)} placeholder="e.g. 2020136N10088" data-testid="image-analysis-storm-id" />
        </label>
        <label>
          <span>Image time, UTC (optional)</span>
          <input className="vd-select" type="datetime-local" value={imageTime} onChange={(event) => setImageTime(event.target.value)} data-testid="image-analysis-time" />
        </label>
      </div>
      <div className="image-analysis-body">
        <label
          htmlFor={inputId}
          className={`image-drop ${dragging ? "image-drop-active" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          data-testid="image-analysis-dropzone"
        >
          {preview ? <img src={preview} alt={file ? `Uploaded image ${file.name}` : "Uploaded image"} /> : (
            <>
              <Upload size={20} />
              <strong>Drop an infrared satellite image</strong>
              <span>or click to choose a file</span>
            </>
          )}
          <input
            id={inputId}
            type="file"
            accept={ACCEPTED_TYPES.join(",")}
            onChange={(event) => { choose(event.target.files?.[0]); event.target.value = ""; }}
            data-testid="image-analysis-input"
          />
        </label>

        <div className="image-analysis-output" aria-live="polite">
          {!file && !localError && (
            <p className="image-analysis-hint">
              The image goes to the identification model; when it finds a cyclone, the intensity classifier runs next.
              Best results come from an 11 µm infrared scene about 18°×18° centred on the system, north up, with cold cloud
              tops bright (GridSat-style). PNG, JPEG, TIFF, BMP or WebP, up to 10 MB.
            </p>
          )}
          {localError && <ErrorNotice copy={{ title: "IMAGE NOT ACCEPTED", message: localError }} />}
          {analysis.isPending && (
            <div className="image-analysis-pending" data-testid="image-analysis-pending"><ScanSearch size={16} /> Analysing {file?.name}…</div>
          )}
          {analysis.isError && (
            <ErrorNotice
              copy={errorCopy(analysis.error)}
              // Retrying helps only for server/network trouble — a rejected file needs a different file.
              onRetry={file && !(analysis.error instanceof ApiError && analysis.error.status >= 400 && analysis.error.status < 500) ? () => analysis.mutate(file) : undefined}
            />
          )}
          {analysis.data && <AnalysisResult result={analysis.data} />}
        </div>
      </div>
    </Panel>
  );
}
