import { LoaderCircle } from "lucide-react";

/** Skeleton rows with a label, sized to sit inside a panel while data loads. */
export default function LoadingBlock({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div className="loading-block" role="status" aria-live="polite" data-testid="loading-block">
      <span className="loading-block-label"><LoaderCircle size={13} className="state-spinner" />{label}</span>
      {Array.from({ length: rows }, (_, index) => <span key={index} className="skeleton-bar" style={{ width: `${88 - index * 16}%` }} />)}
    </div>
  );
}
