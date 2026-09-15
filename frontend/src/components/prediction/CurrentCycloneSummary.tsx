import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatMovement, formatObservedAt } from "@/lib/format";
import { formatLatitude, formatLongitude } from "@/lib/geo";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import type { DataSource } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";

export default function CurrentCycloneSummary({ cyclone, source }: { cyclone: CycloneData; source?: DataSource }) {
  const { preferences } = usePreferences();
  const rows: [string, string, string][] = [
    ["Cyclone ID", cyclone.code, "id"],
    ["Name", cyclone.name, "name"],
    ["Category", cyclone.category ?? "— (no wind recorded)", "category"],
    ["Latitude", formatLatitude(cyclone.location.latitude), "lat"],
    ["Longitude", formatLongitude(cyclone.location.longitude), "lon"],
    ["Wind speed", formatWind(cyclone.windKmh, preferences.windUnit), "wind"],
    ["Pressure", formatPressure(cyclone.pressureHpa, preferences.pressureUnit), "pressure"],
    ["Movement", formatMovement(cyclone.movementDirection, cyclone.movementSpeedKmh), "movement"],
    ["Last observed", formatObservedAt(cyclone.observedAt), "observed"],
    ["Forecast", cyclone.forecastAvailable
      ? `Available — from ${cyclone.forecastOrigin ? formatObservedAt(cyclone.forecastOrigin) : "the latest complete fix"}`
      : "Not possible — no fix has a full 24 h history with wind and pressure", "forecast"],
  ];
  return (
    <Panel eyebrow={`CURRENT STATUS / ${cyclone.code}`} title={`${cyclone.name} · ${cyclone.location.label}`} action={<DataSourceBadge source={source} />} data-testid="current-cyclone-summary">
      <dl className="pred-facts">
        {rows.map(([label, value, key]) => <div key={key}><dt>{label}</dt><dd data-testid={`current-${key}`}>{value}</dd></div>)}
      </dl>
    </Panel>
  );
}
