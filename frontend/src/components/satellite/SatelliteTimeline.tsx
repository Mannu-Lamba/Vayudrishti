import type { KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight, ChevronsRight } from "lucide-react";
import Panel from "@/components/common/Panel";

export type TimelineEntryStatus = "ready" | "processing" | "missing" | "night";

export interface TimelineEntry {
  id: string;
  label: string;
  status: TimelineEntryStatus;
  detail?: string;
}

interface SatelliteTimelineProps {
  entries: TimelineEntry[];
  value?: string;
  onChange: (id: string) => void;
  /** Full timestamp of the selected entry, e.g. "08 SEP 2026 — 14:30 UTC". */
  readout?: string;
  heading?: string;
}

const LEGEND: { status: TimelineEntryStatus; label: string }[] = [
  { status: "ready", label: "Frame ready" },
  { status: "processing", label: "Processing" },
  { status: "missing", label: "Scan gap" },
  { status: "night", label: "Local night (VIS)" },
];

/** Reusable slot timeline: click, arrow keys, or step buttons. */
export default function SatelliteTimeline({ entries, value, onChange, readout, heading = "TIMELINE · UTC" }: SatelliteTimelineProps) {
  const index = entries.findIndex((entry) => entry.id === value);
  const go = (next: number) => {
    const entry = entries[next];
    if (entry) onChange(entry.id);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const moves: Record<string, number> = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: entries.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    go(moves[event.key]);
  };

  return (
    <Panel className="sat-timeline-panel" data-testid="satellite-timeline">
      <div className="sat-timeline" onKeyDown={onKeyDown}>
        <div className="sat-timeline-head">
          <span className="sat-control-label">{heading}</span>
          <strong data-testid="satellite-timeline-readout">{readout ?? "—"}</strong>
        </div>
        <div className="sat-timeline-track" role="group" aria-label="Observation time">
          {entries.map((entry) => {
            const active = entry.id === value;
            return (
              <button
                type="button"
                key={entry.id}
                className={`sat-slot sat-slot-${entry.status} ${active ? "sat-slot-active" : ""}`}
                aria-pressed={active}
                title={entry.detail}
                onClick={() => onChange(entry.id)}
                data-testid={`satellite-timeline-slot-${entry.label.replace(":", "")}`}
              >
                <span className="sat-slot-dot" />
                <span>{entry.label}</span>
              </button>
            );
          })}
        </div>
        <div className="sat-timeline-nav">
          <button type="button" className="icon-button compact" onClick={() => go(index - 1)} disabled={index <= 0} aria-label="Previous frame" data-testid="satellite-timeline-prev"><ChevronLeft size={15} /></button>
          <button type="button" className="icon-button compact" onClick={() => go(index + 1)} disabled={index < 0 || index >= entries.length - 1} aria-label="Next frame" data-testid="satellite-timeline-next"><ChevronRight size={15} /></button>
          <button type="button" className="icon-button compact" onClick={() => go(entries.length - 1)} disabled={index === entries.length - 1} aria-label="Latest frame" data-testid="satellite-timeline-latest"><ChevronsRight size={15} /></button>
        </div>
      </div>
      <div className="sat-timeline-legend">
        {LEGEND.map((item) => <span key={item.status} className={`sat-slot-${item.status}`}><span className="sat-slot-dot" />{item.label}</span>)}
      </div>
    </Panel>
  );
}
