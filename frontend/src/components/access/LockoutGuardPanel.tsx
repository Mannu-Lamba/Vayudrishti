import { useQuery } from "@tanstack/react-query";
import { Lock, ShieldCheck, UserX } from "lucide-react";
import Panel from "@/components/common/Panel";
import { useAuth } from "@/lib/auth";
import { getAccessPolicy } from "@/services/access";

/**
 * Lockout guard section: a read-only explainer of the safeguards the backend already enforces
 * (last-domain removal is rejected, self role changes are blocked) so admins understand why a
 * given action is disabled before they try it.
 */
export default function LockoutGuardPanel() {
  const { user } = useAuth();
  const policy = useQuery({ queryKey: ["access-policy"], queryFn: getAccessPolicy });
  const ownDomain = user?.email.split("@")[1];
  const domainCount = policy.data?.allowed_domains.length ?? 0;

  return (
    <Panel eyebrow="SAFEGUARDS" title="Lockout protection" data-testid="lockout-guard-panel">
      <div className="lockout-guard-body">
        <div className="lockout-guard-item" data-testid="lockout-guard-domain">
          <Lock size={15} />
          <div>
            <strong>Last allowed domain cannot be removed</strong>
            <span>
              {policy.data?.open_access
                ? "Access is currently open — no domain restriction is enforced yet."
                : `${domainCount} domain${domainCount === 1 ? "" : "s"} approved. Removing ${ownDomain ?? "your domain"} while it is the only entry is blocked so the console never goes fully unreachable.`}
            </span>
          </div>
        </div>
        <div className="lockout-guard-item" data-testid="lockout-guard-role">
          <UserX size={15} />
          <div>
            <strong>Administrators cannot demote themselves</strong>
            <span>The role selector for your own row is disabled — a second administrator must change your role, so an account can never strip its own admin access by mistake.</span>
          </div>
        </div>
        <div className="lockout-guard-item" data-testid="lockout-guard-auto">
          <ShieldCheck size={15} />
          <div>
            <strong>Your domain auto-joins the first restriction</strong>
            <span>The first time an open allowlist gets a domain added, {ownDomain ?? "your domain"} is included automatically so the acting admin is never locked out by their own change.</span>
          </div>
        </div>
      </div>
    </Panel>
  );
}
