import Panel from "@/components/common/Panel";
import DataSourceBadge from "@/components/common/DataSourceBadge";
import { formatLatitude, formatLongitude } from "@/lib/geo";
import { formatPressure, formatWind, usePreferences } from "@/lib/preferences";
import type { DataSource } from "@/types/api";
import type { CycloneData } from "@/types/cyclone";

export default function CurrentCycloneSummary({ cyclone, source }: { cyclone: CycloneData; source?: DataSource }) {
  const { preferences } = usePreferences();
  const rows: [string, string, string][] = [
    ["Cyclone ID", cyclone.code, "id"],
    ["Name", cyclone.name, "name"],
    ["Category", cyclone.category, "category"],
    ["Latitude", formatLatitude(cyclone.location.latitude), "lat"],
    ["Longitude", formatLongitude(cyclone.location.longitude), "lon"],
    ["Wind speed", formatWind(cyclone.windKmh, preferences.windUnit), "wind"],
    ["Pressure", formatPressure(cyclone.pressureHpa, preferences.pressureUnit), "pressure"],
    ["Movement", `${cyclone.movementDirection} at ${cyclone.movementSpeedKmh} km/h`, "movement"],
    ["Observed", cyclone.observedAt, "observed"],
  ];
  return (
    <Panel eyebrow={`CURRENT STATUS / ${cyclone.code}`} title={`${cyclone.name} · ${cyclone.location.label}`} action={<DataSourceBadge source={source} />} data-testid="current-cyclone-summary">
      <dl className="pred-facts">
        {rows.map(([label, value, key]) => <div key={key}><dt>{label}</dt><dd data-testid={`current-${key}`}>{value}</dd></div>)}
      </dl>
    </Panel>
  );
}
