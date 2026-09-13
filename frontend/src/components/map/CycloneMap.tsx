import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, setWorkerUrl } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { LoaderCircle, Maximize2, Satellite } from "lucide-react";
import ApiErrorState from "@/components/common/ApiErrorState";
import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { MapContext, type MapLayerToggles } from "./MapContext";
import CycloneMarker from "./CycloneMarker";
import CycloneMarkersLayer from "./CycloneMarkersLayer";
import TrackLayer from "./TrackLayer";
import PredictionLayer from "./PredictionLayer";
import RiskLayer from "./RiskLayer";
import RegionSectorLayer, { type RegionSector } from "./RegionSectorLayer";
import MapControls from "./MapControls";
import MapLegend from "./MapLegend";
import MapTimeline from "./MapTimeline";
import { DEFAULT_VIEWPORT, type MapViewport } from "@/config/mapViewports";
import { inBounds } from "@/lib/geo";
import { darkMapStyle } from "@/lib/mapStyle";
import type { DataSource } from "@/types/api";
import type { CoastalDistrict, CycloneMapScene, MapCycloneMarker, MapDataStatus } from "@/types/track";

// MapLibre 6 derives its worker URL from import.meta.url at runtime, so the production bundle never emitted
// the worker: the request fell through to index.html and every GeoJSON layer (tracks, forecast, risk zones)
// stayed empty. Bundle the worker with Vite and point MapLibre at it — same path in dev and production.
setWorkerUrl(maplibreWorkerUrl);

interface CycloneMapProps {
  /** Every system to draw, e.g. all cyclones in the selected region. */
  cyclones?: MapCycloneMarker[];
  /** The focused system: full marker plus its track, forecast and risk zones. */
  selectedCycloneId?: string | null;
  /** Clicking another system's marker. */
  onCycloneSelect?: (cycloneId: string) => void;
  /** Track, forecast and risk zones of the selected system (lib/mapScene.ts). */
  scene?: CycloneMapScene | null;
  /** Provenance shown in the header badge and popups. */
  dataSource?: DataSource;
  /** Coastal districts for risk-zone impact popups. */
  districts?: CoastalDistrict[];
  /** Loading / error overlay; the map stays visible underneath. */
  status?: MapDataStatus;
  /** Highlighted forecast fix; clicking a fix reports it through onForecastSelect. */
  selectedForecastId?: string;
  onForecastSelect?: (forecastId: string) => void;
  /** Popup provenance line for forecast fixes. */
  forecastLabel?: string;
  /** "panel" = dashboard card height, "full" = tall monitor map, "compact" = side-column map. */
  variant?: "panel" | "full" | "compact";
  showTimeline?: boolean;
  /** Region camera from config/mapViewports.ts. Changing it moves the map. */
  viewport?: MapViewport;
  /** Keep the selected cyclone on screen (pans only when it would be off screen). Off for fixed regional overviews. */
  followCyclone?: boolean;
  eyebrow?: string;
  title?: string;
  tags?: string[];
  /** Subregion outlines (e.g. WP / EP / SP on the Pacific overview). */
  sectors?: RegionSector[];
}

const DEFAULT_TAGS = ["ARABIAN SEA", "BAY OF BENGAL", "INDIAN OCEAN"];
const NO_MARKERS: MapCycloneMarker[] = [];
const NO_DISTRICTS: CoastalDistrict[] = [];
const DATA_LABELS: Record<DataSource, string> = { demo: "DEMO DATA", live: "LIVE API DATA", historical: "HISTORICAL DATA" };

const toLngLatBounds = (viewport: MapViewport): [[number, number], [number, number]] | undefined =>
  viewport.bounds ? [[viewport.bounds.west, viewport.bounds.south], [viewport.bounds.east, viewport.bounds.north]] : undefined;

/** Extra right padding keeps fitted regions clear of the control column. */
const FIT_PADDING = { top: 24, bottom: 24, left: 24, right: 52 };

/** Whether a position is inside the current camera view (view bounds may run past ±180°). */
function isInView(map: MapLibreMap, longitude: number, latitude: number) {
  const bounds = map.getBounds();
  const west = bounds.getWest();
  const lng = ((((longitude - west) % 360) + 360) % 360) + west;
  return latitude >= bounds.getSouth() && latitude <= bounds.getNorth() && lng <= bounds.getEast();
}

function applyViewport(map: MapLibreMap, viewport: MapViewport, duration: number) {
  const bounds = toLngLatBounds(viewport);
  if (bounds) map.fitBounds(bounds, { padding: FIT_PADDING, duration });
  else map.easeTo({ center: viewport.center, zoom: viewport.zoom, duration });
}

/**
 * Presentational MapLibre map. Pages load data through hooks → services and pass it in as markers,
 * a scene, districts and a request status. This component never fetches and does not know whether
 * the data is demo or live — it only shows the provenance it is given.
 */
export default function CycloneMap({
  cyclones = NO_MARKERS,
  selectedCycloneId,
  onCycloneSelect,
  scene = null,
  dataSource,
  districts = NO_DISTRICTS,
  status,
  selectedForecastId,
  onForecastSelect,
  forecastLabel,
  variant = "panel",
  showTimeline = true,
  viewport,
  followCyclone = true,
  eyebrow = "GEOSPATIAL / NORTH INDIAN OCEAN",
  title = "Operational theatre",
  tags = DEFAULT_TAGS,
  sectors,
}: CycloneMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [toggles, setToggles] = useState<MapLayerToggles>({ history: true, prediction: true, risk: true, labels: true });

  const selectedMarker = useMemo(() => cyclones.find((marker) => marker.id === selectedCycloneId) ?? null, [cyclones, selectedCycloneId]);
  const otherMarkers = useMemo(() => cyclones.filter((marker) => marker.id !== selectedCycloneId), [cyclones, selectedCycloneId]);
  // A scene belongs to the selected system; one left over from the previous selection is not drawn.
  const activeScene = scene && (!selectedCycloneId || scene.cycloneId === selectedCycloneId) ? scene : null;

  const timeline = useMemo(() => (activeScene ? [...activeScene.historicalTrack, ...activeScene.forecastPoints] : []), [activeScene]);
  const nowIndex = Math.max(0, timeline.findIndex((point) => point.offsetHours === 0));
  const [selectedIndex, setSelectedIndex] = useState(nowIndex);

  useEffect(() => {
    setSelectedIndex(Math.max(0, timeline.findIndex((point) => point.offsetHours === 0)));
  }, [timeline]);

  const selected = timeline[Math.min(selectedIndex, timeline.length - 1)] ?? timeline[0] ?? null;
  const historyVisible = selected ? timeline.filter((point) => !point.forecast && point.offsetHours <= selected.offsetHours) : [];
  const forecastVisible = selected && activeScene ? activeScene.forecastPoints.filter((point) => point.offsetHours > selected.offsetHours) : [];

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const initial = viewportRef.current ?? DEFAULT_VIEWPORT;
    const bounds = toLngLatBounds(initial);
    const instance = new MapLibreMap({
      container: containerRef.current,
      style: darkMapStyle,
      ...(bounds ? { bounds, fitBoundsOptions: { padding: FIT_PADDING } } : { center: initial.center, zoom: initial.zoom }),
      // Zoom 0 lets the ~185°-wide Pacific overview fit a narrow side-column map.
      minZoom: 0,
      maxZoom: 10,
      attributionControl: false,
      dragRotate: false,
    });
    // Mount overlay layers as soon as the style is parsed — waiting for "load" would
    // stall the whole overlay stack if a basemap tile request is slow.
    const ready = () => { if (instance.isStyleLoaded()) setMap(instance); };
    instance.on("styledata", ready);
    instance.on("load", ready);
    instance.on("error", (event) => console.warn("[map]", event.error?.message));
    if (import.meta.env.DEV) (window as unknown as { __vdMap?: MapLibreMap }).__vdMap = instance;
    mapRef.current = instance;
    return () => {
      instance.remove();
      mapRef.current = null;
      setMap(null);
    };
  }, []);

  // Keyed on the viewport's value, not its identity. Declared before the follow effect so that, when
  // both fire (region switch), centring on an out-of-region cyclone wins over the region fit.
  const viewportKey = viewport ? JSON.stringify(viewport) : "";
  useEffect(() => {
    if (!map || !viewportKey) return;
    applyViewport(map, JSON.parse(viewportKey) as MapViewport, 900);
  }, [map, viewportKey]);

  // Follow the selected cyclone only when it would otherwise be off screen, so the region's other
  // systems stay in view. After a region change the fitted region already shows a cyclone inside it.
  const focusLon = selectedMarker?.longitude ?? activeScene?.currentPosition.longitude;
  const focusLat = selectedMarker?.latitude ?? activeScene?.currentPosition.latitude;
  const followedViewport = useRef(viewportKey);
  useEffect(() => {
    if (!map || !followCyclone || focusLon == null || focusLat == null) return;
    const regionChanged = followedViewport.current !== viewportKey;
    followedViewport.current = viewportKey;
    const regionBounds = viewportKey ? (JSON.parse(viewportKey) as MapViewport).bounds : undefined;
    const shown = regionChanged && regionBounds ? inBounds(regionBounds, focusLat, focusLon) : isInView(map, focusLon, focusLat);
    if (shown) return;
    map.easeTo({ center: [focusLon, focusLat], zoom: Math.max(map.getZoom(), 4.1), duration: 800 });
  }, [map, followCyclone, focusLon, focusLat, viewportKey]);

  const resetView = useCallback(() => {
    if (map) applyViewport(map, viewport ?? DEFAULT_VIEWPORT, 600);
  }, [map, viewport]);

  const toggle = (key: keyof MapLayerToggles) => setToggles((prev) => ({ ...prev, [key]: !prev[key] }));

  const stageClass = variant === "full" ? "map-stage-full" : variant === "compact" ? "map-stage-compact" : "";

  return (
    <Panel
      className={`map-panel ${variant === "full" ? "map-panel-full" : ""} ${variant === "compact" ? "map-panel-compact" : ""}`}
      eyebrow={eyebrow}
      title={title}
      action={<div className="map-actions">
        <DataSourceBadge source={dataSource} />
        <span className="map-attrib"><Satellite size={12} /> OSM dark basemap</span>
        <button type="button" className="icon-button compact" aria-label="Reset map view" onClick={resetView} data-testid="map-expand-button"><Maximize2 size={15} /></button>
      </div>}
      data-testid="cyclone-map-panel"
    >
      <div className={`map-stage map-stage-live ${stageClass}`} data-testid="cyclone-map" aria-busy={status?.loading || undefined}>
        <div ref={containerRef} className="maplibre-canvas" data-testid="maplibre-container" />
        <MapContext.Provider value={map}>
          {map && <>
            {sectors && <RegionSectorLayer sectors={sectors} showLabels={toggles.labels} />}
            {activeScene && <RiskLayer zones={activeScene.riskZones} visible={toggles.risk} districts={districts} />}
            {activeScene && <TrackLayer points={historyVisible} visible={toggles.history} showLabels={toggles.labels} />}
            {activeScene && selected && (
              <PredictionLayer
                origin={selected}
                points={forecastVisible}
                uncertaintyKm={activeScene.uncertaintyKm}
                uncertaintyPolygon={activeScene.uncertaintyPolygon}
                visible={toggles.prediction}
                showLabels={toggles.labels}
                selectedId={selectedForecastId}
                onSelect={onForecastSelect}
                dataLabel={forecastLabel}
              />
            )}
            <CycloneMarkersLayer markers={otherMarkers} showLabels={toggles.labels} onSelect={onCycloneSelect} />
            {selectedMarker && <CycloneMarker key={selectedMarker.id} marker={selectedMarker} position={selected} showLabel={toggles.labels} dataLabel={dataSource ? DATA_LABELS[dataSource] : undefined} />}
            <MapControls toggles={toggles} onToggle={toggle} onReset={resetView} />
          </>}
        </MapContext.Provider>
        <MapLegend />
        <div className="map-basin-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        {status?.loading && (
          <div className="map-status" role="status" data-testid="map-loading">
            <LoaderCircle size={14} className="state-spinner" />{status.loadingLabel ?? "LOADING CYCLONE DATA"}
          </div>
        )}
        {!status?.loading && status?.error ? (
          <div className="map-error-overlay" data-testid="map-error-state">
            <ApiErrorState error={status.error} onRetry={status.onRetry} title="CYCLONE DATA UNAVAILABLE" message="Unable to retrieve cyclone information." />
          </div>
        ) : null}
      </div>
      {showTimeline && timeline.length > 0 && <MapTimeline points={timeline} selectedIndex={Math.min(selectedIndex, timeline.length - 1)} onSelect={setSelectedIndex} />}
    </Panel>
  );
}
