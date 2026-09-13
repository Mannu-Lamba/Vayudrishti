import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Filter, ScrollText, Search, Users } from "lucide-react";
import { toast } from "sonner";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { useAuth } from "@/lib/auth";
import { formatUtc } from "@/lib/time";
import { getAuditEvents, recordClientAudit } from "@/services/access";
import { AUDIT_ACTIONS, describeAction } from "@/types/audit";
import type { AuditEvent, AuditScope } from "@/types/audit";

function summariseDetails(event: AuditEvent): string {
  const entries = Object.entries(event.details).filter(([, value]) => value !== null && value !== "" && value !== undefined);
  if (entries.length === 0) return "";
  return entries.map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`).join(" · ");
}

function exportHandoff(events: AuditEvent[], scope: AuditScope, actor: string) {
  const payload = { platform: "VayuDrishti", exported_at: new Date().toISOString(), exported_by: actor, scope, event_count: events.length, events };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `vayudrishti-handoff-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.json`;
  link.click();
  URL.revokeObjectURL(url);
  recordClientAudit({ action: "briefing.exported", target: "audit-handoff", details: { events: events.length, scope } });
  toast.success("Handoff log exported", { description: `${events.length} events written to a JSON handoff file.` });
}

export default function Audit() {
  const { user, isAdmin } = useAuth();
  const [scope, setScope] = useState<AuditScope>("mine");
  const [action, setAction] = useState("");
  const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["audit", scope, action], queryFn: () => getAuditEvents(scope, action || undefined) });

  const events = useMemo(() => {
    const list = query.data?.events ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((event) => [event.actor_email, event.actor_name, event.action, event.target ?? "", summariseDetails(event)].some((value) => value.toLowerCase().includes(needle)));
  }, [query.data, search]);

  return (
    <div className="page-stack" data-testid="audit-page">
      <div className="page-intro-row">
        <div>
          <div className="section-kicker"><ScrollText size={13} /> AUDIT TRAIL / {String(query.data?.total ?? 0).padStart(3, "0")} EVENTS</div>
          <h2 className="page-heading">Mission audit trail</h2>
          <p className="page-subheading">Important analyst and administrator actions, recorded server-side for transparent shift handoffs.</p>
        </div>
        <button type="button" className="primary-action" disabled={events.length === 0} onClick={() => exportHandoff(events, scope, user?.email ?? "operator")} data-testid="audit-export-button"><Download size={14} />Export handoff log</button>
      </div>

      <div className="audit-toolbar" data-testid="audit-toolbar">
        {isAdmin && (
          <div className="scope-toggle" role="tablist" aria-label="Audit scope">
            <button type="button" role="tab" aria-selected={scope === "mine"} className={scope === "mine" ? "scope-active" : ""} onClick={() => setScope("mine")} data-testid="audit-scope-mine">My actions</button>
            <button type="button" role="tab" aria-selected={scope === "all"} className={scope === "all" ? "scope-active" : ""} onClick={() => setScope("all")} data-testid="audit-scope-all"><Users size={12} /> All operators</button>
          </div>
        )}
        <label className="audit-filter"><Filter size={13} /><select value={action} onChange={(event) => setAction(event.target.value)} aria-label="Filter by action" data-testid="audit-action-filter"><option value="">All actions</option>{Object.entries(AUDIT_ACTIONS).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}</select></label>
        <label className="audit-filter audit-search"><Search size={13} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search actor, target, details" aria-label="Search audit events" data-testid="audit-search-input" /></label>
      </div>

      <Panel eyebrow={scope === "all" ? "ALL OPERATORS" : "YOUR ACTIVITY"} title="Recorded actions" data-testid="audit-panel">
        {query.isLoading && <div className="panel-body"><StateNotice variant="loading" /></div>}
        {query.isError && <div className="panel-body"><StateNotice variant="error" /></div>}
        {query.data && events.length === 0 && <div className="panel-body"><StateNotice variant="empty" /></div>}
        {events.length > 0 && (
          <div className="audit-table-wrap">
            <table className="audit-table" data-testid="audit-table">
              <thead><tr><th>Time (UTC)</th><th>Action</th><th>Actor</th><th>Target</th><th>Details</th></tr></thead>
              <tbody>
                {events.map((event) => {
                  const meta = describeAction(event.action);
                  return (
                    <tr key={event.id} data-testid={`audit-row-${event.id}`}>
                      <td className="audit-time">{formatUtc(event.created_at)}</td>
                      <td><span className={`audit-action audit-action-${meta.tone}`}>{meta.label}</span></td>
                      <td className="audit-actor"><strong>{event.actor_name}</strong><span>{event.actor_email} · {event.actor_role}</span></td>
                      <td className="audit-target">{event.target ?? "—"}</td>
                      <td className="audit-details">{summariseDetails(event) || "—"}{event.ip ? <span className="audit-ip">{event.ip}</span> : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
