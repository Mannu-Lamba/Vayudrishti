import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, LogOut, MonitorSmartphone, ShieldOff, Smartphone, TabletSmartphone } from "lucide-react";
import { toast } from "sonner";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { ApiError } from "@/services/apiClient";
import { endSession } from "@/lib/session";
import { formatRelative, formatUtc } from "@/lib/time";
import { getSessions, revokeOtherSessions, revokeSession } from "@/services/access";
import type { SessionInfo } from "@/types/auth";

function DeviceIcon({ os }: { os: string }) {
  if (os === "iOS" || os === "Android") return <Smartphone size={18} />;
  if (os === "ChromeOS") return <TabletSmartphone size={18} />;
  return <Laptop size={18} />;
}

export default function Sessions() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["sessions"], queryFn: getSessions });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["sessions"] });

  const revokeOne = useMutation({
    mutationFn: (session: SessionInfo) => revokeSession(session.session_id).then(() => session),
    onSuccess: (session) => {
      if (session.current) { void endSession(); return; }
      toast.success("Session revoked", { description: `${session.browser} on ${session.os} was signed out.` });
      void invalidate();
    },
    onError: (error) => toast.error(error instanceof ApiError ? String((error.body as { detail?: string })?.detail ?? "Could not revoke session") : "Could not revoke session"),
  });

  const revokeOthers = useMutation({
    mutationFn: revokeOtherSessions,
    onSuccess: (result) => { toast.success(`${result.revoked} other device${result.revoked === 1 ? "" : "s"} signed out`); void invalidate(); },
    onError: () => toast.error("Could not revoke other sessions"),
  });

  const sessions = query.data?.sessions ?? [];
  const others = sessions.filter((session) => !session.current);

  return (
    <div className="page-stack" data-testid="sessions-page">
      <div className="page-intro-row">
        <div>
          <div className="section-kicker"><MonitorSmartphone size={13} /> SESSION CENTER / {String(sessions.length).padStart(2, "0")} ACTIVE</div>
          <h2 className="page-heading">Active devices</h2>
          <p className="page-subheading">Every device signed into your operator account. Revoke anything you do not recognise — revoked devices are signed out immediately.</p>
        </div>
        <button type="button" className="secondary-action" disabled={others.length === 0 || revokeOthers.isPending} onClick={() => revokeOthers.mutate()} data-testid="revoke-others-button">
          <ShieldOff size={14} />Sign out other devices
        </button>
      </div>

      <Panel eyebrow="OPERATOR SESSIONS" title="Devices with console access" data-testid="sessions-panel">
        {query.isLoading && <div className="panel-body"><StateNotice variant="loading" /></div>}
        {query.isError && <div className="panel-body"><StateNotice variant="error" /></div>}
        {query.data && (
          <div className="session-list">
            {sessions.map((session) => (
              <div key={session.session_id} className={`session-row ${session.current ? "session-row-current" : ""}`} data-testid={`session-row-${session.session_id}`}>
                <div className="session-device-icon"><DeviceIcon os={session.os} /></div>
                <div className="session-copy">
                  <strong>{session.browser} · {session.os} {session.current && <span className="session-current-tag" data-testid="session-current-tag">THIS DEVICE</span>}</strong>
                  <span>IP {session.ip ?? "unknown"} · Signed in {formatUtc(session.created_at)} · Expires {formatUtc(session.expires_at)}</span>
                </div>
                <div className="session-seen"><span className="metric-label">LAST ACTIVE</span><b>{formatRelative(session.last_seen_at)}</b></div>
                <button type="button" className="session-revoke" disabled={revokeOne.isPending} onClick={() => revokeOne.mutate(session)} data-testid={`revoke-session-${session.session_id}`}>
                  <LogOut size={13} />{session.current ? "Sign out" : "Revoke"}
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="registry-footer"><ShieldOff size={13} /> Sessions expire automatically after 7 days. Revocations are recorded in the audit trail.</div>
      </Panel>
    </div>
  );
}
