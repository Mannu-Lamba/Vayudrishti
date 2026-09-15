import { useEffect, useMemo, useRef } from "react";
import { Popup, type ExpressionSpecification, type GeoJSONSource, type MapLayerMouseEvent } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { formatCoords, lineString, pointCollection, polygonFeature, uncertaintyCircles, uncertaintyCorridor } from "@/lib/geo";
import type { GeoTrackPoint } from "@/types/track";

interface PredictionLayerProps {
  origin: GeoTrackPoint;
  points: GeoTrackPoint[];
  uncertaintyKm: { start: number; end: number };
  /** Backend prediction polygon; replaces the corridor when present. */
  uncertaintyPolygon?: [number, number][];
  visible: boolean;
  showLabels: boolean;
  /** Highlighted forecast fix (prediction timeline / detail panel). */
  selectedId?: string;
  onSelect?: (forecastId: string) => void;
  /** Provenance line in the popup, e.g. "DEMO / MOCK MODEL OUTPUT". */
  dataLabel?: string;
}

const CONE_ID = "forecast-cone";
const CIRCLE_ID = "forecast-uncertainty-circles";
const LINE_ID = "forecast-line";
const POINT_ID = "forecast-points";
const LABEL_ID = "forecast-labels";

const SELECTED = ["get", "selected"];
const expr = (value: unknown) => value as ExpressionSpecification;

function popupHtml(point: GeoTrackPoint, dataLabel: string) {
  const uncertainty = point.uncertaintyRadiusKm ? `<div><dt>Uncertainty</dt><dd>±${point.uncertaintyRadiusKm} km</dd></div>` : "";
  return `<div class="map-popup" data-testid="forecast-point-popup">
    <span class="map-popup-eyebrow">FORECAST FIX · ${point.label}</span>
    <strong>${point.timestamp}</strong>
    <dl>
      <div><dt>Position</dt><dd>${formatCoords(point.latitude, point.longitude)}</dd></div>
      <div><dt>Predicted wind</dt><dd>${point.windKmh} km/h</dd></div>
      <div><dt>Pressure</dt><dd>${point.pressureHpa} hPa</dd></div>
      <div><dt>Confidence</dt><dd>${point.confidence == null ? "—" : `${Math.round(point.confidence)}%`}</dd></div>
      ${uncertainty}
    </dl>
    <span class="map-popup-note">${dataLabel}</span>
  </div>`;
}

function coneData(path: GeoTrackPoint[], points: GeoTrackPoint[], uncertaintyKm: { start: number; end: number }, polygon?: [number, number][]) {
  if (polygon?.length) return polygonFeature(polygon);
  const radii = points.map((point) => point.uncertaintyRadiusKm);
  const known = radii.filter((radius): radius is number => radius != null);
  // Per-point radii when the prediction provides them; the origin tapers to half the smallest.
  const widths = known.length ? [Math.min(...known) * 0.5, ...radii] : undefined;
  return uncertaintyCorridor(path, uncertaintyKm.start, uncertaintyKm.end, widths);
}

function circleData(points: GeoTrackPoint[], selectedId?: string) {
  const circles = uncertaintyCircles(points);
  return { ...circles, features: circles.features.map((feature) => ({ ...feature, properties: { ...feature.properties, selected: feature.properties.id === selectedId } })) };
}

const withSelection = (points: GeoTrackPoint[], selectedId?: string) => pointCollection(points.map((point) => ({ ...point, selected: point.id === selectedId })));

export default function PredictionLayer({ origin, points, uncertaintyKm, uncertaintyPolygon, visible, showLabels, selectedId, onSelect, dataLabel = "MODEL FORECAST" }: PredictionLayerProps) {
  const map = useMapInstance();
  const popupRef = useRef<Popup | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const dataLabelRef = useRef(dataLabel);
  dataLabelRef.current = dataLabel;

  const path = useMemo(() => [origin, ...points], [origin, points]);
  const dataRef = useRef({ path, points, uncertaintyKm, uncertaintyPolygon, selectedId });
  dataRef.current = { path, points, uncertaintyKm, uncertaintyPolygon, selectedId };

  useEffect(() => {
    if (!map) return;
    const initial = dataRef.current;
    map.addSource(CONE_ID, { type: "geojson", data: coneData(initial.path, initial.points, initial.uncertaintyKm, initial.uncertaintyPolygon) });
    map.addLayer({
      id: CONE_ID,
      type: "fill",
      source: CONE_ID,
      paint: { "fill-color": "#22d3ee", "fill-opacity": 0.1, "fill-outline-color": "rgba(34,211,238,0.4)" },
    });
    map.addSource(CIRCLE_ID, { type: "geojson", data: circleData(initial.points, initial.selectedId) });
    map.addLayer({
      id: CIRCLE_ID,
      type: "line",
      source: CIRCLE_ID,
      paint: {
        "line-color": expr(["case", SELECTED, "#f59e0b", "#22d3ee"]),
        "line-opacity": expr(["case", SELECTED, 0.9, 0.35]),
        "line-width": expr(["case", SELECTED, 1.4, 1]),
        "line-dasharray": [2, 2],
      },
    });
    map.addSource(LINE_ID, { type: "geojson", data: lineString(initial.path) });
    map.addLayer({
      id: LINE_ID,
      type: "line",
      source: LINE_ID,
      layout: { "line-cap": "round" },
      paint: { "line-color": "#22d3ee", "line-width": 2.4, "line-dasharray": [2, 1.6] },
    });
    map.addSource(POINT_ID, { type: "geojson", data: withSelection(initial.points, initial.selectedId) });
    map.addLayer({
      id: POINT_ID,
      type: "circle",
      source: POINT_ID,
      paint: {
        "circle-radius": expr(["case", SELECTED, 8.5, 6]),
        "circle-color": expr(["case", SELECTED, "#f59e0b", "#06202c"]),
        "circle-stroke-color": expr(["case", SELECTED, "#fde68a", "#22d3ee"]),
        "circle-stroke-width": expr(["case", SELECTED, 2.5, 2]),
      },
    });
    map.addLayer({
      id: LABEL_ID,
      type: "symbol",
      source: POINT_ID,
      layout: {
        "text-field": ["get", "label"],
        "text-size": 10,
        "text-offset": [0, -1.4],
        "text-anchor": "bottom",
        "text-allow-overlap": true,
      },
      paint: { "text-color": expr(["case", SELECTED, "#fde68a", "#7dd3fc"]), "text-halo-color": "#050b12", "text-halo-width": 1.3 },
    });

    const onClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const point = feature.properties as unknown as GeoTrackPoint;
      popupRef.current?.remove();
      popupRef.current = new Popup({ closeButton: true, className: "vd-popup", offset: 14 })
        .setLngLat([point.longitude, point.latitude])
        .setHTML(popupHtml(point, dataLabelRef.current))
        .addTo(map);
      onSelectRef.current?.(point.id);
    };
    const enter = () => { map.getCanvas().style.cursor = "pointer"; };
    const leave = () => { map.getCanvas().style.cursor = ""; };
    map.on("click", POINT_ID, onClick);
    map.on("mouseenter", POINT_ID, enter);
    map.on("mouseleave", POINT_ID, leave);

    return () => {
      map.off("click", POINT_ID, onClick);
      map.off("mouseenter", POINT_ID, enter);
      map.off("mouseleave", POINT_ID, leave);
      popupRef.current?.remove();
      popupRef.current = null;
      [LABEL_ID, POINT_ID, LINE_ID, CIRCLE_ID, CONE_ID].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      [POINT_ID, LINE_ID, CIRCLE_ID, CONE_ID].forEach((id) => {
        if (map.getSource(id)) map.removeSource(id);
      });
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const cone = map.getSource(CONE_ID) as GeoJSONSource | undefined;
    const circles = map.getSource(CIRCLE_ID) as GeoJSONSource | undefined;
    const line = map.getSource(LINE_ID) as GeoJSONSource | undefined;
    const pts = map.getSource(POINT_ID) as GeoJSONSource | undefined;
    if (cone && "setData" in cone) cone.setData(coneData(path, points, uncertaintyKm, uncertaintyPolygon));
    if (circles && "setData" in circles) circles.setData(circleData(points, selectedId));
    if (line && "setData" in line) line.setData(lineString(path));
    if (pts && "setData" in pts) pts.setData(withSelection(points, selectedId));
  }, [map, path, points, uncertaintyKm, uncertaintyPolygon, selectedId]);

  useEffect(() => {
    if (!map) return;
    [CONE_ID, CIRCLE_ID, LINE_ID, POINT_ID].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    });
    if (map.getLayer(LABEL_ID)) map.setLayoutProperty(LABEL_ID, "visibility", visible && showLabels ? "visible" : "none");
  }, [map, visible, showLabels]);

  return null;
}
