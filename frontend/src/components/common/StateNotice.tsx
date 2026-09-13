import { AlertCircle, CloudOff, Database, ImageOff, LoaderCircle, SatelliteDish, ScanSearch, SearchX, Waves } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type StateNoticeVariant =
  | "loading"
  | "empty"
  | "error"
  | "unavailable"
  | "offline"
  | "no-source"
  | "no-imagery"
  | "no-cyclone"
  | "no-systems";

const stateConfig: Record<StateNoticeVariant, { icon: LucideIcon; label: string; text: string }> = {
  loading: { icon: LoaderCircle, label: "LOADING TELEMETRY", text: "Waiting for the observation service to respond." },
  empty: { icon: SearchX, label: "NO SYSTEMS FOUND", text: "No active systems match the current filter." },
  error: { icon: AlertCircle, label: "DATA LINK INTERRUPTED", text: "The latest observation could not be retrieved." },
  unavailable: { icon: Database, label: "DATA UNAVAILABLE", text: "This channel is reserved for a future operational feed." },
  offline: { icon: CloudOff, label: "API NOT CONNECTED", text: "Serving local mock observations. Live satellite and cyclone services connect in Phase 4." },
  "no-source": { icon: SatelliteDish, label: "NO SATELLITE SOURCE AVAILABLE", text: "No configured geostationary source covers this sector." },
  "no-imagery": { icon: ImageOff, label: "NO IMAGERY FOR SELECTED TIMESTAMP", text: "This source did not deliver a frame for the selected time." },
  "no-cyclone": { icon: ScanSearch, label: "NO CYCLONE DETECTED", text: "No tropical cyclone signature in this frame." },
  "no-systems": { icon: Waves, label: "REGION HAS NO ACTIVE CYCLONES", text: "No active tropical cyclones are being tracked in this sector." },
};

interface StateNoticeProps {
  variant: StateNoticeVariant;
  /** Override the default copy for context-specific messages. */
  title?: string;
  message?: string;
  action?: ReactNode;
}

export default function StateNotice({ variant, title, message, action }: StateNoticeProps) {
  const config = stateConfig[variant];
  const Icon = config.icon;
  return <div className="state-notice" data-testid={`state-${variant}`}><Icon size={18} className={variant === "loading" ? "state-spinner" : ""} /><div><strong>{title ?? config.label}</strong><span>{message ?? config.text}</span>{action && <div className="state-notice-action">{action}</div>}</div></div>;
}
