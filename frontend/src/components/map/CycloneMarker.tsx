import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { Marker } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { categoryColor } from "@/config/cycloneCategories";
import { formatCoords } from "@/lib/geo";
import type { GeoTrackPoint, MapCycloneMarker } from "@/types/track";

interface CycloneMarkerProps {
  marker: MapCycloneMarker;
  /** Timeline fix to draw at; until the track loads the marker sits at the registry position. */
  position: GeoTrackPoint | null;
  showLabel: boolean;
  /** Provenance line for the popup, e.g. "DEMO DATA". */
  dataLabel?: string;
}

/** The selected system: full marker with a details popup, coloured by the API category. */
export default function CycloneMarker({ marker, position, showLabel, dataLabel }: CycloneMarkerProps) {
  const map = useMapInstance();
  const element = useMemo(() => document.createElement("div"), []);
  const markerRef = useRef<Marker | null>(null);
  const latitude = position?.latitude ?? marker.latitude;
  const longitude = position?.longitude ?? marker.longitude;
  const lngLatRef = useRef<[number, number]>([longitude, latitude]);
  lngLatRef.current = [longitude, latitude];
  const [popupOpen, setPopupOpen] = useState(false);

  useEffect(() => {
    if (!map) return;
    element.className = "vd-marker-anchor";
    markerRef.current = new Marker({ element, anchor: "center" }).setLngLat(lngLatRef.current).addTo(map);
    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
    };
  }, [map, element]);

  useEffect(() => {
    markerRef.current?.setLngLat([longitude, latitude]);
  }, [longitude, latitude]);

  // A past fix may carry its own category from the backend; otherwise the registry category applies.
  const category = position?.category ?? marker.category;
  const windKmh = position?.windKmh ?? marker.windKmh;
  const pressureHpa = position?.pressureHpa ?? marker.pressureHpa;
  const time = position?.timestamp ?? marker.observedAt;
  const style = { "--vd-marker": categoryColor(category) } as CSSProperties;

  return createPortal(
    <div className="vd-marker" style={style} data-cyclone-id={marker.id} data-category={category}>
      <button
        type="button"
        className="vd-marker-button"
        aria-label={`${marker.code} ${marker.name}, ${category} — details`}
        onClick={() => setPopupOpen((open) => !open)}
        data-testid="map-cyclone-marker"
      >
        <span className="vd-marker-pulse" />
        <span className="vd-marker-ring" />
        <span className="vd-marker-core">
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <path d="M12 3c4 0 7 2.2 7 5 0 2.2-2 3.6-4.6 3.9 1.7.5 2.9 1.7 2.9 3.3 0 2.3-2.3 4.1-5.3 4.1-4 0-7-2.2-7-5 0-2.2 2-3.6 4.6-3.9C7.9 9.9 6.7 8.7 6.7 7.1 6.7 4.8 9 3 12 3Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <circle cx="12" cy="12" r="1.6" fill="currentColor" />
          </svg>
        </span>
      </button>
      {showLabel && !popupOpen && (
        <span className="vd-marker-label" data-testid="map-cyclone-marker-label">
          {marker.code} · {windKmh} km/h
        </span>
      )}
      {popupOpen && (
        <div className="map-popup vd-marker-popup" data-testid="cyclone-marker-popup">
          <button type="button" className="vd-popup-close" onClick={() => setPopupOpen(false)} aria-label="Close cyclone popup" data-testid="cyclone-popup-close">×</button>
          <span className="map-popup-eyebrow">{`${marker.status.toUpperCase()} SYSTEM${position ? ` · ${position.label}` : ""}`}</span>
          <strong>{marker.code} · {marker.name}</strong>
          <dl>
            <div><dt>Category</dt><dd>{category}</dd></div>
            <div><dt>Wind</dt><dd>{windKmh} km/h</dd></div>
            <div><dt>Pressure</dt><dd>{pressureHpa} hPa</dd></div>
            <div><dt>Position</dt><dd>{formatCoords(latitude, longitude)}</dd></div>
            {time && <div><dt>Time</dt><dd>{time}</dd></div>}
            {position?.confidence != null && <div><dt>Detection confidence</dt><dd>{position.confidence}%</dd></div>}
          </dl>
          {dataLabel && <span className="map-popup-note">{dataLabel}</span>}
        </div>
      )}
    </div>,
    element,
  );
}
