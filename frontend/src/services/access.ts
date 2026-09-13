// Access-control boundary: sessions, audit trail, and admin policy all ride the httpOnly cookie.
import { apiDelete, apiGet, apiPatch, apiPost } from "@/services/apiClient";
import type { AuditEvent, AuditEventCreate, AuditListResponse, AuditScope } from "@/types/audit";
import type { AccessPolicy, ManagedUser, RevokeOthersResponse, Role, SessionListResponse } from "@/types/auth";

export const getSessions = () => apiGet<SessionListResponse>("/sessions");
export const revokeSession = (sessionId: string) => apiDelete<void>(`/sessions/${sessionId}`);
export const revokeOtherSessions = () => apiPost<RevokeOthersResponse>("/sessions/revoke-others");

export function getAuditEvents(scope: AuditScope, action?: string): Promise<AuditListResponse> {
  const params = new URLSearchParams({ scope, limit: "200" });
  if (action) params.set("action", action);
  return apiGet<AuditListResponse>(`/audit/events?${params.toString()}`);
}

// Fire-and-forget: an audit write must never interrupt the operator's action.
export function recordClientAudit(event: AuditEventCreate): void {
  void apiPost<AuditEvent>("/audit/events", event).catch(() => undefined);
}

export const getAccessPolicy = () => apiGet<AccessPolicy>("/admin/access-policy");
export const addAllowedDomain = (domain: string) => apiPost<AccessPolicy>("/admin/access-policy/domains", { domain });
export const removeAllowedDomain = (domain: string) => apiDelete<AccessPolicy>(`/admin/access-policy/domains/${encodeURIComponent(domain)}`);
export const getManagedUsers = () => apiGet<ManagedUser[]>("/admin/users");
export const updateUserRole = (userId: string, role: Role) => apiPatch<ManagedUser>(`/admin/users/${userId}/role`, { role });
