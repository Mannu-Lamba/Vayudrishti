import { useEffect, useRef } from "react";
import { Popup, type GeoJSONSource, type MapLayerMouseEvent } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { categoryColorExpression } from "@/config/cycloneCategories";
import { formatCoords } from "@/lib/geo";
import { escapeHtml } from "@/lib/html";
import type { MapCycloneMarker } from "@/types/track";

const SOURCE_ID = "cyclone-markers";
const HALO_ID = "cyclone-markers-halo";
const DOT_ID = "cyclone-markers-dot";
const LABEL_ID = "cyclone-markers-label";

function markerCollection(markers: MapCycloneMarker[]) {
  return {
    type: "FeatureCollection" as const,
    features: markers.map((marker) => ({
      type: "Feature" as const,
      properties: { id: marker.id, code: marker.code, category: marker.category, status: marker.status, windKmh: marker.windKmh },
      geometry: { type: "Point" as const, coordinates: [marker.longitude, marker.latitude] },
    })),
  };
}

function hoverHtml(marker: MapCycloneMarker) {
  return `<div class="map-popup map-popup-compact" data-testid="cyclone-hover-popup">
    <span class="map-popup-eyebrow">${escapeHtml(marker.status.toUpperCase())} SYSTEM · CLICK TO SELECT</span>
    <strong>${escapeHtml(marker.code)} · ${escapeHtml(marker.name)}</strong>
    <dl>
      <div><dt>Category</dt><dd>${escapeHtml(marker.category ?? "—")}</dd></div>
      <div><dt>Wind</dt><dd>${marker.windKmh == null ? "—" : `${escapeHtml(marker.windKmh)} km/h`}</dd></div>
      <div><dt>Pressure</dt><dd>${marker.pressureHpa == null ? "—" : `${escapeHtml(marker.pressureHpa)} hPa`}</dd></div>
      <div><dt>Position</dt><dd>${escapeHtml(formatCoords(marker.latitude, marker.longitude))}</dd></div>
    </dl>
  </div>`;
}

interface CycloneMarkersLayerProps {
  /** Every system except the selected one (which gets the full DOM marker). */
  markers: MapCycloneMarker[];
  showLabels: boolean;
  onSelect?: (cycloneId: string) => void;
}

/** One GeoJSON point per system, coloured by the API category. Hover shows details; click selects. */
export default function CycloneMarkersLayer({ markers, showLabels, onSelect }: CycloneMarkersLayerProps) {
  const map = useMapInstance();
  const markersRef = useRef(markers);
  markersRef.current = markers;
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!map) return;
    map.addSource(SOURCE_ID, { type: "geojson", data: markerCollection(markersRef.current) });
    map.addLayer({ id: HALO_ID, type: "circle", source: SOURCE_ID, paint: { "circle-radius": 13, "circle-color": categoryColorExpression, "circle-opacity": 0.18 } });
    map.addLayer({
      id: DOT_ID,
      type: "circle",
      source: SOURCE_ID,
      paint: { "circle-radius": 6, "circle-color": categoryColorExpression, "circle-stroke-color": "#0e1013", "circle-stroke-width": 1.5 },
    });
    map.addLayer({
      id: LABEL_ID,
      type: "symbol",
      source: SOURCE_ID,
      layout: {
        "text-field": ["concat", ["get", "code"], " · ", ["to-string", ["get", "windKmh"]], " km/h"],
        "text-size": 10,
        "text-offset": [0, 1.4],
        "text-anchor": "top",
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#d6dade", "text-halo-color": "#0e1013", "text-halo-width": 1.2 },
    });

    const hover = new Popup({ closeButton: false, closeOnClick: false, offset: 14, className: "vd-popup vd-hover-popup", maxWidth: "260px" });
    const markerAt = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id;
      return typeof id === "string" ? markersRef.current.find((marker) => marker.id === id) : undefined;
    };
    const onClick = (event: MapLayerMouseEvent) => {
      const marker = markerAt(event);
      if (!marker) return;
      hover.remove();
      onSelectRef.current?.(marker.id);
    };
    const onMove = (event: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = "pointer";
      const marker = markerAt(event);
      if (marker) hover.setLngLat([marker.longitude, marker.latitude]).setHTML(hoverHtml(marker)).addTo(map);
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = "";
      hover.remove();
    };
    [HALO_ID, DOT_ID].forEach((id) => {
      map.on("click", id, onClick);
      map.on("mousemove", id, onMove);
      map.on("mouseleave", id, onLeave);
    });

    return () => {
      [HALO_ID, DOT_ID].forEach((id) => {
        map.off("click", id, onClick);
        map.off("mousemove", id, onMove);
        map.off("mouseleave", id, onLeave);
      });
      hover.remove();
      [LABEL_ID, DOT_ID, HALO_ID].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    if (source && "setData" in source) source.setData(markerCollection(markers));
  }, [map, markers]);

  useEffect(() => {
    if (!map || !map.getLayer(LABEL_ID)) return;
    map.setLayoutProperty(LABEL_ID, "visibility", showLabels ? "visible" : "none");
  }, [map, showLabels]);

  return null;
}
