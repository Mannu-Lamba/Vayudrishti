import { useEffect, useRef } from "react";
import { Popup, type ExpressionSpecification, type GeoJSONSource, type MapLayerMouseEvent } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { districtsInRiskZone, riskCollection } from "@/lib/geo";
import type { CoastalDistrict, CoastalImpact, RiskZoneSpec } from "@/types/track";

const SOURCE_ID = "risk-zones";
const FILL_ID = "risk-zones-fill";
const LINE_ID = "risk-zones-outline";

const LEVEL_COLOR = [
  "match",
  ["get", "level"],
  "severe", "#ef4444",
  "high", "#f59e0b",
  "moderate", "#38bdf8",
  "#22d3ee",
] as unknown as ExpressionSpecification;

function impactPopupHtml(zoneLabel: string, level: string, radiusKm: number, impacts: CoastalImpact[]) {
  const rows = impacts.length
    ? impacts
        .map(
          (impact) =>
            `<div data-testid="coastal-impact-district-${impact.district.id}"><dt>${impact.district.name}, ${impact.district.state}</dt><dd>${impact.distanceKm.toFixed(0)} km</dd></div>`,
        )
        .join("")
    : `<div data-testid="coastal-impact-empty"><dt>No listed coastal district inside this radius</dt><dd>—</dd></div>`;
  return `<div class="map-popup" data-testid="risk-zone-popup">
    <span class="map-popup-eyebrow">RISK ZONE · ${level.toUpperCase()}</span>
    <strong>${zoneLabel}</strong>
    <dl>
      <div><dt>Radius</dt><dd>${radiusKm} km</dd></div>
    </dl>
    <span class="map-popup-note">COASTAL DISTRICTS IN RANGE (${impacts.length})</span>
    <dl class="map-popup-impact-list">${rows}</dl>
    <span class="map-popup-note">MOCK IMPACT ESTIMATE — CENTROID DISTANCE ONLY</span>
  </div>`;
}

export default function RiskLayer({ zones, visible, districts }: { zones: RiskZoneSpec[]; visible: boolean; districts: CoastalDistrict[] }) {
  const map = useMapInstance();
  const zonesRef = useRef(zones);
  zonesRef.current = zones;
  const districtsRef = useRef(districts);
  districtsRef.current = districts;
  const popupRef = useRef<Popup | null>(null);

  useEffect(() => {
    if (!map) return;
    map.addSource(SOURCE_ID, { type: "geojson", data: riskCollection(zonesRef.current) });
    map.addLayer({
      id: FILL_ID,
      type: "fill",
      source: SOURCE_ID,
      paint: { "fill-color": LEVEL_COLOR, "fill-opacity": 0.11 },
    });
    map.addLayer({
      id: LINE_ID,
      type: "line",
      source: SOURCE_ID,
      paint: { "line-color": LEVEL_COLOR, "line-width": 1.1, "line-opacity": 0.55 },
    });

    const onClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      // Forecast fixes and other-system markers sit on top of risk zones; their clicks are theirs.
      const above = ["forecast-points", "cyclone-markers-dot", "cyclone-markers-halo"].filter((id) => map.getLayer(id));
      if (above.length && map.queryRenderedFeatures(event.point, { layers: above }).length) return;
      const props = feature.properties as { id: string; level: string; label: string; radiusKm: number; centerLat: number; centerLng: number };
      const impacts = districtsInRiskZone({ latitude: props.centerLat, longitude: props.centerLng }, props.radiusKm, districtsRef.current);
      popupRef.current?.remove();
      popupRef.current = new Popup({ closeButton: true, className: "vd-popup", offset: 8, maxWidth: "260px" })
        .setLngLat(event.lngLat)
        .setHTML(impactPopupHtml(props.label, props.level, props.radiusKm, impacts))
        .addTo(map);
    };
    const enter = () => { map.getCanvas().style.cursor = "pointer"; };
    const leave = () => { map.getCanvas().style.cursor = ""; };
    map.on("click", FILL_ID, onClick);
    map.on("mouseenter", FILL_ID, enter);
    map.on("mouseleave", FILL_ID, leave);

    return () => {
      map.off("click", FILL_ID, onClick);
      map.off("mouseenter", FILL_ID, enter);
      map.off("mouseleave", FILL_ID, leave);
      popupRef.current?.remove();
      popupRef.current = null;
      [FILL_ID, LINE_ID].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    if (source && "setData" in source) source.setData(riskCollection(zones));
  }, [map, zones]);

  useEffect(() => {
    if (!map) return;
    [FILL_ID, LINE_ID].forEach((id) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    });
    if (!visible) popupRef.current?.remove();
  }, [map, visible]);

  return null;
}
