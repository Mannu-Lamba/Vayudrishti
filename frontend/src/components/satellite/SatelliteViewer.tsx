import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Crosshair, ImageOff, LoaderCircle, Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";
import Panel from "@/components/common/Panel";
import { projectToFrame } from "@/lib/geo";
import { bandLabel, formatFrameTimestamp, formatUtcClock, UNAVAILABLE_SHORT } from "@/lib/satellite";
import type { SatelliteSource } from "@/types/region";
import type { SatelliteChannelId, SatelliteChannelSpec, SatelliteObservation } from "@/types/satellite";

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.5;

const SCALE_ENDS: Record<SatelliteChannelId, [string, string]> = {
  infrared: ["+20°C", "−80°C"],
  water_vapor: ["DRY", "MOIST"],
  visible: ["LOW", "HIGH ALBEDO"],
};

interface ViewerState {
  testId: string;
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

interface SatelliteViewerProps {
  /** Metadata of the selected frame (from the catalog). */
  observation?: SatelliteObservation | null;
  /** Fetched frame with `imageUrl`; may still be the previous frame while the next one loads. */
  frame?: SatelliteObservation | null;
  isFetching: boolean;
  isCatalogLoading: boolean;
  hasSource: boolean;
  source?: SatelliteSource;
  channel?: SatelliteChannelSpec;
  regionLabel: string;
  subregionLabel?: string;
  focusedCycloneId?: string;
  onSwitchChannel?: (channel: SatelliteChannelId) => void;
  onJumpToAvailable?: () => void;
}

function unavailableState(observation: SatelliteObservation, source: SatelliteSource | undefined, onSwitchChannel?: (channel: SatelliteChannelId) => void, onJump?: () => void): ViewerState {
  const name = source?.name ?? "This source";
  const time = formatUtcClock(observation.timestamp);
  switch (observation.unavailableReason) {
    case "local_night":
      return {
        testId: "state-night",
        title: "VISIBLE CHANNEL UNAVAILABLE — LOCAL NIGHT",
        message: `Local solar time ${observation.localSolarTime ?? "—"} at the sector centre. Visible imagery needs daylight; infrared and water vapor are unaffected.`,
        actionLabel: "Switch to infrared",
        onAction: onSwitchChannel ? () => onSwitchChannel("infrared") : undefined,
      };
    case "scan_gap":
      return {
        testId: "state-no-imagery",
        title: "NO IMAGERY FOR SELECTED TIMESTAMP",
        message: `${name} did not deliver the ${time} scan (mock scan gap).`,
        actionLabel: "Jump to nearest available frame",
        onAction: onJump,
      };
    case "processing":
      return {
        testId: "state-processing",
        title: "FRAME PROCESSING",
        message: `${name} ${time} scan received — calibration and navigation (L1C) are still running.`,
        actionLabel: "Show nearest available frame",
        onAction: onJump,
      };
    default:
      return { testId: "state-unavailable", title: "SATELLITE UNAVAILABLE", message: `${name} has no usable frame for this time.` };
  }
}

export default function SatelliteViewer({
  observation,
  frame,
  isFetching,
  isCatalogLoading,
  hasSource,
  source,
  channel,
  regionLabel,
  subregionLabel,
  focusedCycloneId,
  onSwitchChannel,
  onJumpToAvailable,
}: SatelliteViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [loadedUrl, setLoadedUrl] = useState<string>();
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const clampPan = (next: { x: number; y: number }, scale: number) => {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return next;
    const maxX = ((scale - 1) * rect.width) / 2;
    const maxY = ((scale - 1) * rect.height) / 2;
    return { x: Math.max(-maxX, Math.min(maxX, next.x)), y: Math.max(-maxY, Math.min(maxY, next.y)) };
  };

  const applyZoom = (next: number) => {
    const scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, next));
    setZoom(scale);
    setPan((current) => clampPan(current, scale));
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (zoom <= MIN_ZOOM) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    setDragging(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragRef.current;
    if (!start) return;
    setPan(clampPan({ x: start.panX + event.clientX - start.x, y: start.panY + event.clientY - start.y }, zoom));
  };
  const endDrag = () => {
    dragRef.current = null;
    setDragging(false);
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    else void containerRef.current?.requestFullscreen?.().catch(() => undefined);
  };

  const band = channel ? source?.channels[channel.id] : undefined;
  const available = Boolean(observation?.available);
  const currentFrame = frame && observation && frame.id === observation.id ? frame : undefined;
  const shownFrame = frame?.imageUrl ? frame : undefined;
  const imageReady = Boolean(currentFrame?.imageUrl && loadedUrl === currentFrame.imageUrl);
  const loading = isCatalogLoading || (hasSource && available && (isFetching || !imageReady));
  const detections = imageReady && currentFrame?.bounds ? currentFrame.detections ?? [] : [];

  let state: ViewerState | null = null;
  if (!isCatalogLoading) {
    if (!hasSource) state = { testId: "state-no-source", title: "NO SATELLITE SOURCE AVAILABLE", message: "No configured geostationary source covers this sector." };
    else if (!observation) state = { testId: "state-unavailable", title: "SATELLITE UNAVAILABLE", message: `${source?.name ?? "This source"} has no ${channel?.label.toLowerCase() ?? "selected"} band for this sector.` };
    else if (!observation.available) state = unavailableState(observation, source, onSwitchChannel, onJumpToAvailable);
  }

  const statusBadge = !observation ? null : observation.available
    ? <span className="status-badge status-badge-green"><span className="status-dot status-dot-green" />PROCESSED</span>
    : <span className="status-badge status-badge-amber"><span className="status-dot status-dot-amber" />{observation.unavailableReason ? UNAVAILABLE_SHORT[observation.unavailableReason] : "UNAVAILABLE"}</span>;

  return (
    <Panel
      className="sat-viewer-panel"
      eyebrow={`PRIMARY VIEWER / ${source?.name ?? "NO SOURCE"}${channel ? ` · ${channel.shortLabel}` : ""}`}
      title="Satellite imagery"
      action={statusBadge}
      data-testid="satellite-hero-panel"
    >
      <div ref={containerRef} className={`sat-viewer ${fullscreen ? "sat-viewer-fullscreen" : ""}`} data-testid="satellite-viewer">
        <div
          ref={stageRef}
          className={`sat-viewer-stage ${zoom > MIN_ZOOM ? "sat-viewer-pannable" : ""} ${dragging ? "sat-viewer-dragging" : ""}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={() => applyZoom(zoom + ZOOM_STEP)}
        >
          <div className={`sat-viewer-canvas ${loading && shownFrame ? "sat-viewer-dim" : ""}`} style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
            {available && shownFrame?.imageUrl && (
              <img
                src={shownFrame.imageUrl}
                alt={`Mock ${channel?.label.toLowerCase() ?? ""} render of the ${regionLabel} sector from ${source?.name ?? "an unknown source"}`}
                draggable={false}
                onLoad={() => setLoadedUrl(shownFrame.imageUrl)}
                data-testid="satellite-viewer-image"
              />
            )}
            {currentFrame?.bounds && detections.map((detection) => {
              const position = projectToFrame(currentFrame.bounds!, detection.latitude, detection.longitude);
              return (
                <span
                  key={detection.cycloneId}
                  className={`sat-detection ${detection.cycloneId === focusedCycloneId ? "sat-detection-focused" : ""}`}
                  style={{ left: `${position.x * 100}%`, top: `${position.y * 100}%`, transform: `translate(-50%, -50%) scale(${1 / zoom})` }}
                  data-testid={`satellite-detection-${detection.cycloneId}`}
                >
                  <Crosshair size={20} />
                  <span>{detection.code}<small>{detection.confidence.toFixed(0)}%</small></span>
                </span>
              );
            })}
          </div>
        </div>

        <div className="sat-viewer-ident" data-testid="satellite-viewer-overlay">
          <strong>{source?.name ?? "NO SOURCE"}</strong>
          <span>{channel?.label.toUpperCase() ?? "—"}{band ? ` · ${bandLabel(band)}` : ""}</span>
          <span>{regionLabel.toUpperCase()}{subregionLabel ? ` › ${subregionLabel.toUpperCase()}` : ""}</span>
          <time dateTime={observation?.timestamp}>{formatFrameTimestamp(observation?.timestamp)}</time>
        </div>

        <div className="sat-viewer-tools">
          <div className="map-control-group">
            <button type="button" onClick={() => applyZoom(zoom + ZOOM_STEP)} disabled={zoom >= MAX_ZOOM} aria-label="Zoom in" data-testid="satellite-zoom-in"><Plus size={14} /></button>
            <button type="button" onClick={() => applyZoom(zoom - ZOOM_STEP)} disabled={zoom <= MIN_ZOOM} aria-label="Zoom out" data-testid="satellite-zoom-out"><Minus size={14} /></button>
            <button type="button" onClick={() => { setZoom(MIN_ZOOM); setPan({ x: 0, y: 0 }); }} aria-label="Reset zoom" data-testid="satellite-zoom-reset"><RotateCcw size={13} /></button>
          </div>
          <div className="map-control-group">
            <button type="button" onClick={toggleFullscreen} aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"} aria-pressed={fullscreen} data-testid="satellite-fullscreen"><>{fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}</></button>
          </div>
          {zoom > MIN_ZOOM && <span className="sat-zoom-readout" data-testid="satellite-zoom-level">{zoom.toFixed(1)}×</span>}
        </div>

        {available && imageReady && (
          <div className="sat-viewer-foot">
            <span className="sat-viewer-badge">MOCK IMAGERY · NOT SATELLITE DATA</span>
            <span className={`sat-viewer-detect ${detections.length ? "" : "sat-viewer-detect-none"}`} data-testid={detections.length ? "satellite-detection-count" : "state-no-cyclone"}>
              {detections.length ? `${detections.length} SYSTEM${detections.length > 1 ? "S" : ""} DETECTED` : "NO CYCLONE DETECTED"}
            </span>
            {channel && <span className={`sat-scale sat-scale-${channel.id}`}><span>{SCALE_ENDS[channel.id][0]}</span><i /><span>{SCALE_ENDS[channel.id][1]}</span></span>}
          </div>
        )}

        {loading && !state && <div className="sat-viewer-loading" data-testid="state-loading"><LoaderCircle size={15} className="state-spinner" />ACQUIRING FRAME…</div>}

        {state && (
          <div className="sat-viewer-state" data-testid={state.testId}>
            <div className="sat-viewer-state-card">
              <ImageOff size={22} />
              <strong>{state.title}</strong>
              <p>{state.message}</p>
              {state.actionLabel && state.onAction && <button type="button" className="secondary-action" onClick={state.onAction} data-testid="satellite-viewer-state-action">{state.actionLabel}</button>}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
