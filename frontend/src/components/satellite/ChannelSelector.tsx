import { bandLabel } from "@/lib/satellite";
import type { SatelliteSource } from "@/types/region";
import type { SatelliteChannelId, SatelliteChannelSpec } from "@/types/satellite";

interface ChannelSelectorProps {
  channels: SatelliteChannelSpec[];
  source?: SatelliteSource;
  value: SatelliteChannelId;
  onChange: (channel: SatelliteChannelId) => void;
}

export default function ChannelSelector({ channels, source, value, onChange }: ChannelSelectorProps) {
  return (
    <div className="segmented" role="group" aria-label="Channel" data-testid="satellite-channel-selector">
      {channels.map((channel) => {
        const band = source?.channels[channel.id];
        const active = channel.id === value;
        return (
          <button
            type="button"
            key={channel.id}
            className={active ? "segmented-active" : ""}
            aria-pressed={active}
            disabled={!band}
            onClick={() => onChange(channel.id)}
            title={channel.description}
            data-testid={`satellite-band-${channel.shortLabel.toLowerCase()}-button`}
          >
            <strong>{channel.label.toUpperCase()}</strong>
            <small>{band ? bandLabel(band) : "Not on this source"}</small>
          </button>
        );
      })}
    </div>
  );
}
