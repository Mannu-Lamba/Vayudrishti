import { useEffect, useRef } from "react";
import type { GeoJSONSource } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { lineString, pointCollection } from "@/lib/geo";
import type { GeoTrackPoint } from "@/types/track";

interface TrackLayerProps {
  points: GeoTrackPoint[];
  visible: boolean;
  showLabels: boolean;
}

const LINE_ID = "history-line";
const POINT_ID = "history-points";
const LABEL_ID = "history-labels";

export default function TrackLayer({ points, visible, showLabels }: TrackLayerProps) {
  const map = useMapInstance();
  // Layer setup runs once per map; the data effect below owns every later update.
  const pointsRef = useRef(points);
  pointsRef.current = points;

  useEffect(() => {
    if (!map) return;
    if (!map.getSource(LINE_ID)) {
      map.addSource(LINE_ID, { type: "geojson", data: lineString(pointsRef.current) });
      map.addLayer({
        id: LINE_ID,
        type: "line",
        source: LINE_ID,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#94a3b8", "line-width": 2.2, "line-opacity": 0.85 },
      });
    }
    if (!map.getSource(POINT_ID)) {
      map.addSource(POINT_ID, { type: "geojson", data: pointCollection(pointsRef.current) });
      map.addLayer({
        id: POINT_ID,
        type: "circle",
        source: POINT_ID,
        paint: {
          "circle-radius": 4,
          "circle-color": "#0b1622",
          "circle-stroke-color": "#cbd5e1",
          "circle-stroke-width": 1.6,
        },
      });
      map.addLayer({
        id: LABEL_ID,
        type: "symbol",
        source: POINT_ID,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 9,
          "text-offset": [0, 1.3],
          "text-anchor": "top",
          "text-allow-overlap": true,
        },
        paint: { "text-color": "#94a3b8", "text-halo-color": "#050b12", "text-halo-width": 1.2 },
      });
    }
    return () => {
      [LABEL_ID, POINT_ID, LINE_ID].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      [POINT_ID, LINE_ID].forEach((id) => {
        if (map.getSource(id)) map.removeSource(id);
      });
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const lineSource = map.getSource(LINE_ID) as GeoJSONSource | undefined;
    const pointSource = map.getSource(POINT_ID) as GeoJSONSource | undefined;
    if (lineSource && "setData" in lineSource) lineSource.setData(lineString(points));
    if (pointSource && "setData" in pointSource) pointSource.setData(pointCollection(points));
  }, [map, points]);

  useEffect(() => {
    if (!map) return;
    [LINE_ID, POINT_ID].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    });
    if (map.getLayer(LABEL_ID)) map.setLayoutProperty(LABEL_ID, "visibility", visible && showLabels ? "visible" : "none");
  }, [map, visible, showLabels]);

  return null;
}
