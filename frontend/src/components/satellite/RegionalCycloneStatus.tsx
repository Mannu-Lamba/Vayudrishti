import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { formatCoordsCompact } from "@/lib/geo";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import { padCount } from "@/lib/regions";
import type { RiskLevel } from "@/types/cyclone";
import type { RegionalCycloneObservation } from "@/types/region";

const RISK_TONE: Record<RiskLevel, string> = { severe: "red", high: "amber", moderate: "cyan", low: "green" };

interface RegionalCycloneStatusProps {
  observation?: RegionalCycloneObservation;
  isLoading: boolean;
  regionLabel: string;
  slotLabel?: string;
  season?: string;
  focusedId?: string;
  onFocus: (cycloneId: string) => void;
}

export default function RegionalCycloneStatus({ observation, isLoading, regionLabel, slotLabel, season, focusedId, onFocus }: RegionalCycloneStatusProps) {
  const { preferences } = usePreferences();
  const systems = observation?.systems ?? [];
  const strongest = observation?.strongest;
  return (
    <Panel
      className="obs-panel"
      eyebrow={`CYCLONE OBSERVATION · ${slotLabel ?? "—"} UTC`}
      title={regionLabel.toUpperCase()}
      action={<span className={`status-badge ${systems.length ? "status-badge-amber" : "status-badge-green"}`}>{padCount(systems.length)} ACTIVE</span>}
      data-testid="regional-cyclone-status"
    >
      {isLoading && !observation ? (
        <div className="panel-body"><StateNotice variant="loading" /></div>
      ) : !strongest ? (
        <div className="panel-body">
          <StateNotice variant="no-systems" message={`No active tropical cyclones in the ${regionLabel} at this time.${season ? ` Season: ${season}.` : ""}`} />
        </div>
      ) : (
        <>
          <div className="obs-stat-grid">
            <div className="obs-stat"><span className="metric-label">Active systems</span><strong data-testid="obs-active-count">{padCount(systems.length)}</strong></div>
            <div className="obs-stat"><span className="metric-label">Strongest system</span><strong data-testid="obs-strongest-code">{strongest.code}</strong><small>{strongest.name}</small></div>
            <div className="obs-stat obs-stat-wide"><span className="metric-label">Category</span><strong>{strongest.category}</strong></div>
            <div className="obs-stat"><span className="metric-label">Max wind</span><strong>{formatWind(strongest.windKmh, preferences.windUnit)}</strong></div>
            <div className="obs-stat"><span className="metric-label">Pressure</span><strong>{formatPressure(strongest.pressureHpa, preferences.pressureUnit)}</strong></div>
          </div>
          <div className="obs-system-list">
            {systems.map((system) => (
              <button
                type="button"
                key={system.cycloneId}
                className={`obs-system ${system.cycloneId === focusedId ? "obs-system-active" : ""}`}
                aria-pressed={system.cycloneId === focusedId}
                onClick={() => onFocus(system.cycloneId)}
                data-testid={`obs-system-${system.cycloneId}`}
              >
                <span className={`status-dot status-dot-${RISK_TONE[system.riskLevel]}`} />
                <span className="obs-system-id">
                  <strong>{system.code} · {system.name}</strong>
                  <small>{system.category} · {formatCoordsCompact(system.latitude, system.longitude)}</small>
                </span>
                <span className="obs-system-wind">{formatWind(system.windKmh, preferences.windUnit)}<small>{system.confidence.toFixed(1)}% conf.</small></span>
              </button>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}
