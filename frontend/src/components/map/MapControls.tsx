import { Crosshair, Layers, Minus, Plus, Route, ShieldAlert, Tag } from "lucide-react";
import { useMapInstance } from "./MapContext";
import type { MapLayerToggles } from "./MapContext";
import { THEATRE_VIEW } from "@/lib/mapStyle";

interface MapControlsProps {
  toggles: MapLayerToggles;
  onToggle: (key: keyof MapLayerToggles) => void;
  /** Region-aware reset; defaults to the North Indian Ocean theatre view. */
  onReset?: () => void;
}

const TOGGLE_META: { key: keyof MapLayerToggles; label: string; icon: typeof Route }[] = [
  { key: "history", label: "Historical track", icon: Route },
  { key: "prediction", label: "Predicted track", icon: Layers },
  { key: "risk", label: "Risk zone", icon: ShieldAlert },
  { key: "labels", label: "Labels", icon: Tag },
];

export default function MapControls({ toggles, onToggle, onReset }: MapControlsProps) {
  const map = useMapInstance();
  const reset = () => (onReset ? onReset() : map?.easeTo({ ...THEATRE_VIEW, duration: 600 }));

  return (
    <div className="map-control-stack" data-testid="map-controls">
      <div className="map-control-group">
        <button type="button" onClick={() => map?.zoomIn()} aria-label="Zoom in" data-testid="map-zoom-in-button"><Plus size={14} /></button>
        <button type="button" onClick={() => map?.zoomOut()} aria-label="Zoom out" data-testid="map-zoom-out-button"><Minus size={14} /></button>
        <button type="button" onClick={reset} aria-label="Reset view" data-testid="map-reset-view-button"><Crosshair size={14} /></button>
      </div>
      <div className="map-control-group map-toggle-group">
        {TOGGLE_META.map(({ key, label, icon: Icon }) => (
          <button
            type="button"
            key={key}
            className={toggles[key] ? "map-toggle-active" : ""}
            onClick={() => onToggle(key)}
            aria-pressed={toggles[key]}
            title={label}
            aria-label={`Toggle ${label}`}
            data-testid={`map-toggle-${key}-button`}
          >
            <Icon size={13} />
          </button>
        ))}
      </div>
    </div>
  );
}
