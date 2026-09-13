import { createContext, useContext } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

export const MapContext = createContext<MapLibreMap | null>(null);

export function useMapInstance() {
  return useContext(MapContext);
}

export interface MapLayerToggles {
  history: boolean;
  prediction: boolean;
  risk: boolean;
  labels: boolean;
}
