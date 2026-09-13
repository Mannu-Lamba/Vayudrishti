import { useEffect, useRef } from "react";
import type { ExpressionSpecification, GeoJSONSource } from "maplibre-gl";
import { useMapInstance } from "./MapContext";
import { boundsRing } from "@/lib/geo";
import type { MapBounds } from "@/types/region";

/** A dashed subregion outline, e.g. Arabian Sea / Bay of Bengal, or WP / EP / SP on the Pacific overview. */
export interface RegionSector {
  id: string;
  label: string;
  bounds: MapBounds;
  active: boolean;
}

const SOURCE_ID = "region-sectors";
const LABEL_SOURCE_ID = "region-sector-labels";
const FILL_ID = "region-sectors-fill";
const LINE_ID = "region-sectors-line";
const LABEL_ID = "region-sectors-label";

const expr = (value: unknown) => value as ExpressionSpecification;
const ACTIVE = ["get", "active"];

function sectorPolygons(sectors: RegionSector[]) {
  return {
    type: "FeatureCollection" as const,
    features: sectors.map((sector) => ({
      type: "Feature" as const,
      properties: { id: sector.id, active: sector.active },
      geometry: { type: "Polygon" as const, coordinates: [boundsRing(sector.bounds)] },
    })),
  };
}

function sectorLabels(sectors: RegionSector[]) {
  return {
    type: "FeatureCollection" as const,
    features: sectors.map((sector) => {
      const { north, south, east, west } = sector.bounds;
      return {
        type: "Feature" as const,
        properties: { label: sector.label.toUpperCase(), active: sector.active },
        geometry: { type: "Point" as const, coordinates: [(west + east) / 2, north - (north - south) * 0.07] },
      };
    }),
  };
}

export default function RegionSectorLayer({ sectors, showLabels }: { sectors: RegionSector[]; showLabels: boolean }) {
  const map = useMapInstance();
  const sectorsRef = useRef(sectors);
  sectorsRef.current = sectors;

  useEffect(() => {
    if (!map) return;
    map.addSource(SOURCE_ID, { type: "geojson", data: sectorPolygons(sectorsRef.current) });
    map.addSource(LABEL_SOURCE_ID, { type: "geojson", data: sectorLabels(sectorsRef.current) });
    map.addLayer({ id: FILL_ID, type: "fill", source: SOURCE_ID, paint: { "fill-color": "#22d3ee", "fill-opacity": expr(["case", ACTIVE, 0.06, 0]) } });
    map.addLayer({
      id: LINE_ID,
      type: "line",
      source: SOURCE_ID,
      paint: { "line-color": expr(["case", ACTIVE, "#22d3ee", "#5b7488"]), "line-width": expr(["case", ACTIVE, 1.4, 1]), "line-opacity": 0.75, "line-dasharray": [3, 3] },
    });
    map.addLayer({
      id: LABEL_ID,
      type: "symbol",
      source: LABEL_SOURCE_ID,
      layout: { "text-field": ["get", "label"], "text-size": 10, "text-letter-spacing": 0.18, "text-allow-overlap": true },
      paint: { "text-color": expr(["case", ACTIVE, "#67e8f9", "#7f97ab"]), "text-halo-color": "#050b12", "text-halo-width": 1.2 },
    });
    return () => {
      [LABEL_ID, LINE_ID, FILL_ID].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
      [LABEL_SOURCE_ID, SOURCE_ID].forEach((id) => {
        if (map.getSource(id)) map.removeSource(id);
      });
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const polygons = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    const labels = map.getSource(LABEL_SOURCE_ID) as GeoJSONSource | undefined;
    if (polygons && "setData" in polygons) polygons.setData(sectorPolygons(sectors));
    if (labels && "setData" in labels) labels.setData(sectorLabels(sectors));
  }, [map, sectors]);

  useEffect(() => {
    if (!map || !map.getLayer(LABEL_ID)) return;
    map.setLayoutProperty(LABEL_ID, "visibility", showLabels ? "visible" : "none");
  }, [map, showLabels]);

  return null;
}
