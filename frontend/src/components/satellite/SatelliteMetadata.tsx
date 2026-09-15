import { Info } from "lucide-react";
import Panel from "@/components/common/Panel";
import { formatLongitude } from "@/lib/geo";
import { bandLabel, formatFrameTimestamp, TIER_LABEL } from "@/lib/satellite";
import type { SelectionDetails } from "@/lib/regions";
import type { SatelliteSource } from "@/types/region";
import type { SatelliteChannelSpec, SatelliteObservation } from "@/types/satellite";

interface SatelliteMetadataProps {
  observation?: SatelliteObservation | null;
  source?: SatelliteSource;
  channel?: SatelliteChannelSpec;
  details: SelectionDetails;
}

/** Mirrors the planned GET /api/satellite/{source}/{timestamp} payload; absent fields show "—". */
export default function SatelliteMetadata({ observation, source, channel, details }: SatelliteMetadataProps) {
  const band = channel ? source?.channels[channel.id] : undefined;
  const rows: [string, string | undefined][] = [
    ["Satellite", source ? `${source.name}${source.serviceSlot ? ` · ${source.serviceSlot}` : ""}` : undefined],
    ["Agency / provider", source ? `${source.agency}${source.dataProvider ? ` · ${source.dataProvider}` : ""}` : undefined],
    ["Instrument", source?.instrument],
    ["Sub-satellite point", source ? (source.subSatelliteLongitude == null ? "— (merged multi-satellite product)" : `0.0° / ${formatLongitude(source.subSatelliteLongitude)}`) : undefined],
    ["Channel / band", channel ? `${channel.label} · ${bandLabel(band)}` : undefined],
    ["Spatial resolution", observation?.resolution ?? (band ? `${band.resolutionKm} km` : undefined)],
    ["Scan cadence", source?.cadenceMinutes != null ? `${source.cadenceMinutes} min` : undefined],
    ["Frame time", observation ? formatFrameTimestamp(observation.timestamp) : undefined],
    ["Coverage", observation?.coverage ? `${observation.coverage}${observation.coverageTier ? ` · ${TIER_LABEL[observation.coverageTier]}` : ""}` : undefined],
    ["Processing", observation ? [observation.processingLevel, observation.processingStatus].filter(Boolean).join(" · ") || undefined : undefined],
    ["Local solar time", observation?.localSolarTime],
    ["Frame id", observation?.id],
    ["Data layer", details.basins.length ? `IBTrACS BASIN = ${details.basins.join(" + ")}` : undefined],
    ["Warning centre", details.rsmc],
  ];
  return (
    <Panel eyebrow="SATELLITE METADATA" title={`${source?.name ?? "No source"} · ${channel?.label ?? "—"}`} data-testid="satellite-metadata">
      <dl className="sat-meta-grid">
        {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? "—"}</dd></div>)}
      </dl>
      {channel && (
        <div className="sat-channel-note" data-testid="satellite-channel-description">
          <Info size={15} />
          <div><strong>{channel.label} channel</strong><p>{channel.description}</p></div>
        </div>
      )}
    </Panel>
  );
}
