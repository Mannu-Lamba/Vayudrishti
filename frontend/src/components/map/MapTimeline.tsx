import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import type { GeoTrackPoint } from "@/types/track";

interface MapTimelineProps {
  points: GeoTrackPoint[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

const SPEED_OPTIONS = [0.5, 1, 2, 4];

export default function MapTimeline({ points, selectedIndex, onSelect }: MapTimelineProps) {
  const active = points[selectedIndex];
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const indexRef = useRef(selectedIndex);
  indexRef.current = selectedIndex;
  const firstPointId = points[0]?.id;

  // Stop the sweep whenever the underlying track changes (e.g. a different cyclone selected).
  useEffect(() => { setIsPlaying(false); }, [firstPointId]);

  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(() => {
      const next = indexRef.current + 1;
      if (next >= points.length) { setIsPlaying(false); return; }
      onSelect(next);
    }, 1000 / speed);
    return () => clearInterval(id);
  }, [isPlaying, speed, points.length, onSelect]);

  const togglePlay = () => {
    if (!isPlaying && selectedIndex >= points.length - 1) onSelect(0);
    setIsPlaying((prev) => !prev);
  };

  return (
    <div className="map-timeline" data-testid="map-timeline">
      <div className="map-timeline-head">
        <span className="map-timeline-eyebrow">TIMELINE</span>
        <strong data-testid="map-timeline-readout">{active.label} · {active.timestamp}</strong>
      </div>
      <div className="map-timeline-transport">
        <button
          type="button"
          className="map-timeline-play"
          onClick={togglePlay}
          aria-label={isPlaying ? "Pause track sweep" : "Play track sweep"}
          aria-pressed={isPlaying}
          data-testid="map-timeline-play-button"
        >
          {isPlaying ? <Pause size={13} /> : <Play size={13} />}
        </button>
        <input
          type="range"
          min={0}
          max={points.length - 1}
          step={1}
          value={selectedIndex}
          onChange={(event) => onSelect(Number(event.target.value))}
          aria-label="Cyclone timeline scrubber"
          data-testid="map-timeline-scrubber"
        />
        <label className="map-timeline-speed">
          <span>SPEED</span>
          <input
            type="range"
            min={0}
            max={SPEED_OPTIONS.length - 1}
            step={1}
            value={SPEED_OPTIONS.indexOf(speed)}
            onChange={(event) => setSpeed(SPEED_OPTIONS[Number(event.target.value)])}
            aria-label="Track sweep speed"
            aria-valuetext={`${speed}×`}
            data-testid="map-timeline-speed-slider"
          />
          <output data-testid="map-timeline-speed-readout">{speed}×</output>
        </label>
      </div>
      <div className="map-timeline-ticks">
        {points.map((point, index) => (
          <button
            type="button"
            key={point.id}
            className={index === selectedIndex ? "timeline-tick-active" : ""}
            onClick={() => onSelect(index)}
            data-testid={`map-timeline-tick-${point.label.replace(/[+·\s]/g, "").toLowerCase()}`}
          >
            {point.label}
          </button>
        ))}
      </div>
    </div>
  );
}
