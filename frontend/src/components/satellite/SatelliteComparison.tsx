import { LoaderCircle } from "lucide-react";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { bandLabel, formatUtcClock, TIER_LABEL, UNAVAILABLE_SHORT } from "@/lib/satellite";
import type { SatelliteCoverageTier, SatelliteSource } from "@/types/region";
import type { SatelliteChannelSpec, SatelliteObservation } from "@/types/satellite";

export interface ComparisonCard {
  source: SatelliteSource;
  tier?: SatelliteCoverageTier;
  note?: string;
  /** Frame metadata for this source at the selected slot and channel. */
  observation?: SatelliteObservation;
  /** Fetched frame with image, when available. */
  frame?: SatelliteObservation | null;
  isLoading: boolean;
}

interface SatelliteComparisonProps {
  cards: ComparisonCard[];
  activeSourceId?: string;
  channel?: SatelliteChannelSpec;
  slotLabel?: string;
  onSelect: (sourceId: string) => void;
}

function Thumb({ card }: { card: ComparisonCard }) {
  const { observation, frame, isLoading } = card;
  if (observation?.available && frame?.imageUrl && frame.id === observation.id) {
    return <img src={frame.imageUrl} alt={`Mock thumbnail from ${card.source.name}`} draggable={false} />;
  }
  if (observation?.available && isLoading) {
    return <span className="sat-compare-thumb-state"><LoaderCircle size={14} className="state-spinner" />ACQUIRING</span>;
  }
  const reason = observation?.unavailableReason;
  return <span className="sat-compare-thumb-state">{reason ? UNAVAILABLE_SHORT[reason] : "NO FRAME"}</span>;
}

export default function SatelliteComparison({ cards, activeSourceId, channel, slotLabel, onSelect }: SatelliteComparisonProps) {
  return (
    <Panel
      eyebrow={`SATELLITE COMPARISON / ${channel?.shortLabel ?? "—"} · ${slotLabel ?? "—"} UTC SLOT`}
      title="Multi-source view"
      action={<span className="mock-badge">{cards.length} SOURCE{cards.length === 1 ? "" : "S"}</span>}
      data-testid="satellite-comparison"
    >
      {cards.length === 0 ? (
        <div className="panel-body"><StateNotice variant="no-source" /></div>
      ) : (
        <div className="sat-compare-row">
          {cards.map((card) => {
            const active = card.source.id === activeSourceId;
            const band = channel ? card.source.channels[channel.id] : undefined;
            return (
              <button
                type="button"
                key={card.source.id}
                className={`sat-compare-card ${active ? "sat-compare-card-active" : ""}`}
                aria-pressed={active}
                onClick={() => onSelect(card.source.id)}
                data-testid={`satellite-compare-${card.source.id}`}
              >
                <span className="sat-compare-thumb">
                  <Thumb card={card} />
                  {active && <span className="sat-compare-primary">PRIMARY VIEWER</span>}
                </span>
                <span className="sat-compare-body">
                  <span className="sat-compare-name">
                    <strong>{card.source.name}</strong>
                    {card.tier && <span className={`tier-badge tier-${card.tier}`}>{TIER_LABEL[card.tier]}</span>}
                  </span>
                  <span className="sat-compare-meta">
                    <span>{channel?.shortLabel ?? "—"} · {bandLabel(band)}</span>
                    <span>{formatUtcClock(card.observation?.timestamp)}</span>
                  </span>
                  <small>{card.note ?? `${card.source.agency} · ${card.source.instrument}`}</small>
                </span>
              </button>
            );
          })}
        </div>
      )}
      {cards.length === 1 && <div className="panel-note">Only one geostationary source covers this sector with usable geometry.</div>}
    </Panel>
  );
}
