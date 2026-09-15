import { AlertTriangle, RotateCcw } from "lucide-react";
import { describeApiError } from "@/services/apiClient";

interface ApiErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  /** What failed to load, e.g. "the prediction". */
  subject?: string;
  /** Replace the generic heading, e.g. "CYCLONE DATA UNAVAILABLE". */
  title?: string;
  /** Replace the generic explanation. */
  message?: string;
}

/** Friendly API failure with Retry. Never shows raw errors, and never substitutes demo data. */
export default function ApiErrorState({ error, onRetry, subject, title, message }: ApiErrorStateProps) {
  const copy = describeApiError(error);
  return (
    <div className="api-error-state" role="alert" data-testid="api-error-state">
      <AlertTriangle size={18} />
      <div>
        <strong>{title ?? copy.title}</strong>
        <span>{message ?? `${copy.message}${subject ? ` Unable to load ${subject}.` : ""}`}</span>
        <div className="api-error-actions">
          {onRetry && <button type="button" className="secondary-action" onClick={onRetry} data-testid="api-error-retry"><RotateCcw size={13} />Retry</button>}
        </div>
      </div>
    </div>
  );
}
