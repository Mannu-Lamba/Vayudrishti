/** Cyclone spiral used as the VayuDrishti mark (three counter-clockwise turns, as in the northern hemisphere). */
export default function BrandMark({ className = "vd-glyph" }: { className?: string }) {
  return (
    <svg className={className} viewBox="4 3 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" aria-hidden="true">
      <path d="M14 12A2 2 0 0 0 10 12A4 4 0 0 0 18 12A6 6 0 0 0 6 12" />
      <circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}
