import { BrainCircuit, RotateCcw, Satellite as SatelliteIcon } from "lucide-react";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import Panel from "@/components/common/Panel";
import { categoryColor } from "@/config/cycloneCategories";
import { formatCoords } from "@/lib/geo";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import type { DataSource } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";

interface TrackState {
  /** Observed fixes returned by the track endpoint. */
  fixes: number;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}

interface CycloneDetailPanelProps {
  cyclone: CycloneData;
  source?: DataSource;
  regionName?: string;
  subregionName?: string;
  track: TrackState;
  hasPrediction: boolean;
  /** Only true when the classification service returned a result for this cyclone. */
  classificationAvailable: boolean;
  onViewSatellite: () => void;
  onViewClassification: () => void;
}

/** The registry record of the selected cyclone, plus the state of its track and forecast. */
export default function CycloneDetailPanel({ cyclone, source, regionName, subregionName, track, hasPrediction, classificationAvailable, onViewSatellite, onViewClassification }: CycloneDetailPanelProps) {
  const { preferences } = usePreferences();
  const status = cyclone.status.charAt(0).toUpperCase() + cyclone.status.slice(1);
  let trackText;
  if (track.loading) trackText = "Loading track…";
  else if (track.error) trackText = <>Track unavailable <button type="button" className="text-action" onClick={track.onRetry} data-testid="detail-track-retry"><RotateCcw size={12} />Retry</button></>;
  else trackText = `Track · ${track.fixes} observed fix${track.fixes === 1 ? "" : "es"}`;

  return (
    <Panel eyebrow={`SELECTED CYCLONE / ${cyclone.code}`} title={`${cyclone.code} · ${cyclone.name}`} action={<DataSourceBadge source={source} />} data-testid="selected-cyclone-detail">
      <dl className="pred-facts cyclone-detail-facts">
        <div><dt>Cyclone ID</dt><dd data-testid="detail-id">{cyclone.code}</dd></div>
        <div><dt>Name</dt><dd data-testid="detail-name">{cyclone.name}</dd></div>
        <div><dt>Category</dt><dd data-testid="detail-category"><span className="category-dot" style={{ background: categoryColor(cyclone.category) }} />{cyclone.category}</dd></div>
        <div><dt>Status</dt><dd data-testid="detail-status">{status}</dd></div>
        <div><dt>Wind</dt><dd data-testid="detail-wind">{formatWind(cyclone.windKmh, preferences.windUnit)}</dd></div>
        <div><dt>Pressure</dt><dd data-testid="detail-pressure">{formatPressure(cyclone.pressureHpa, preferences.pressureUnit)}</dd></div>
        <div><dt>Coordinates</dt><dd data-testid="detail-coordinates">{formatCoords(cyclone.location.latitude, cyclone.location.longitude)}</dd></div>
        <div><dt>Observed</dt><dd data-testid="detail-timestamp">{cyclone.observedAt}</dd></div>
        <div><dt>Region</dt><dd data-testid="detail-region">{regionName ?? "—"}</dd></div>
        <div><dt>Subregion</dt><dd data-testid="detail-subregion">{subregionName ?? "—"}</dd></div>
        <div><dt>IBTrACS basin</dt><dd data-testid="detail-basin">{cyclone.basin}</dd></div>
        <div><dt>Movement</dt><dd>{cyclone.movementDirection} at {cyclone.movementSpeedKmh} km/h</dd></div>
      </dl>
      <div className="cyclone-detail-foot">
        <div className="cyclone-detail-status">
          <span data-testid="detail-track-status">{trackText}</span>
          <span data-testid="detail-forecast-status">{hasPrediction ? "Forecast from the prediction service" : "No prediction available — no forecast drawn"}</span>
        </div>
        <div className="cyclone-detail-actions">
          <button type="button" className="secondary-action" onClick={onViewSatellite} data-testid="detail-view-satellite"><SatelliteIcon size={14} /> VIEW SATELLITE</button>
          <button type="button" className="primary-action" onClick={onViewClassification} disabled={!classificationAvailable} title={classificationAvailable ? undefined : "No classification is available for this cyclone"} data-testid="detail-view-classification"><BrainCircuit size={14} /> VIEW CLASSIFICATION</button>
        </div>
      </div>
    </Panel>
  );
}
