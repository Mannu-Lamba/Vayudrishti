import type { StyleSpecification } from "maplibre-gl";

/**
 * Dark command-center basemap. OSM raster tiles, desaturated + darkened via raster paint
 * so no API key is required. Swap `sources` for a vector/satellite provider later.
 */
export const darkMapStyle: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 18,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#050b12" } },
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint: {
        "raster-opacity": 0.34,
        "raster-saturation": -1,
        "raster-brightness-max": 0.42,
        "raster-contrast": 0.2,
      },
    },
  ],
};

/** North Indian Ocean theatre: India, Arabian Sea, Bay of Bengal, Indian Ocean. */
export const THEATRE_VIEW = { center: [80.5, 13.5] as [number, number], zoom: 3.7 };
