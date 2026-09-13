// Mirrors backend/models/audit.py
export type ClientAuditAction = "cyclone.selected" | "satellite.layer_changed" | "preferences.saved" | "briefing.exported";

export type AuditScope = "mine" | "all";

export interface AuditEvent {
  id: string;
  actor_user_id?: string | null;
  actor_email: string;
  actor_name: string;
  actor_role: string;
  action: string;
  target?: string | null;
  details: Record<string, unknown>;
  ip?: string | null;
  created_at: string;
}

export interface AuditEventCreate {
  action: ClientAuditAction;
  target?: string | null;
  details?: Record<string, unknown>;
}

export interface AuditListResponse {
  events: AuditEvent[];
  scope: AuditScope;
  total: number;
}

export interface AuditActionMeta {
  label: string;
  tone: "cyan" | "amber" | "red" | "green" | "muted";
}

// Human labels for every action the backend records (server + client side).
export const AUDIT_ACTIONS: Record<string, AuditActionMeta> = {
  "auth.sign_in": { label: "Signed in", tone: "green" },
  "auth.sign_out": { label: "Signed out", tone: "muted" },
  "auth.sign_in_denied": { label: "Sign-in denied", tone: "red" },
  "session.revoked": { label: "Session revoked", tone: "amber" },
  "session.revoked_others": { label: "Other devices revoked", tone: "amber" },
  "analyst.requested": { label: "Claude analyst requested", tone: "cyan" },
  "admin.domain_added": { label: "Domain approved", tone: "green" },
  "admin.domain_removed": { label: "Domain removed", tone: "red" },
  "admin.role_changed": { label: "Operator role changed", tone: "amber" },
  "cyclone.selected": { label: "Cyclone inspected", tone: "cyan" },
  "satellite.layer_changed": { label: "Satellite layer switched", tone: "cyan" },
  "preferences.saved": { label: "Preferences saved", tone: "muted" },
  "briefing.exported": { label: "Briefing exported", tone: "cyan" },
};

export function describeAction(action: string): AuditActionMeta {
  return AUDIT_ACTIONS[action] ?? { label: action, tone: "muted" };
}
