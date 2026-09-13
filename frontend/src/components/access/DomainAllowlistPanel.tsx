import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe2, KeyRound, Plus, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { errorDetail } from "@/lib/errors";
import { useAuth } from "@/lib/auth";
import { formatUtc } from "@/lib/time";
import { addAllowedDomain, getAccessPolicy, removeAllowedDomain } from "@/services/access";

/** Domain allowlist section: approve/remove team domains that may sign in. */
export default function DomainAllowlistPanel() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [domain, setDomain] = useState("");
  const policy = useQuery({ queryKey: ["access-policy"], queryFn: getAccessPolicy });
  const refreshPolicy = () => { void queryClient.invalidateQueries({ queryKey: ["access-policy"] }); void queryClient.invalidateQueries({ queryKey: ["audit"] }); };

  const addDomain = useMutation({
    mutationFn: addAllowedDomain,
    onSuccess: (result, added) => {
      setDomain("");
      refreshPolicy();
      const own = user?.email.split("@")[1];
      const autoIncluded = own && own !== added && result.allowed_domains.includes(own) && !policy.data?.allowed_domains.includes(own);
      toast.success(`${added} approved`, { description: autoIncluded ? `${own} was kept on the allowlist automatically so you stay signed in.` : `${result.allowed_domains.length} domain${result.allowed_domains.length === 1 ? "" : "s"} may now sign in.` });
    },
    onError: (error) => toast.error(errorDetail(error, "Could not add domain")),
  });
  const removeDomain = useMutation({
    mutationFn: removeAllowedDomain,
    onSuccess: (_result, removed) => { refreshPolicy(); toast(`${removed} removed from the allowlist`); },
    onError: (error) => toast.error(errorDetail(error, "Could not remove domain")),
  });

  const submitDomain = (event: FormEvent) => { event.preventDefault(); if (domain.trim()) addDomain.mutate(domain.trim().toLowerCase()); };
  const domains = policy.data?.allowed_domains ?? [];

  return (
    <Panel
      eyebrow="DOMAIN ALLOWLIST"
      title="Approved team domains"
      data-testid="domain-policy-panel"
      action={
        <span className={`status-badge ${policy.data?.open_access ? "status-badge-amber" : "status-badge-green"}`} data-testid="access-mode-badge">
          <span className={`status-dot ${policy.data?.open_access ? "status-dot-amber" : "status-dot-green"}`} />{policy.data ? (policy.data.open_access ? "OPEN ACCESS" : `${domains.length} APPROVED`) : "LOADING"}
        </span>
      }
    >
      <form className="domain-form" onSubmit={submitDomain}>
        <label className="audit-filter audit-search"><Globe2 size={13} /><input value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="e.g. sih-team.ac.in" aria-label="Domain to approve" data-testid="domain-input" /></label>
        <button type="submit" className="primary-action" disabled={!domain.trim() || addDomain.isPending} data-testid="domain-add-button"><Plus size={14} />Approve domain</button>
      </form>
      {policy.isLoading && <div className="panel-body"><StateNotice variant="loading" /></div>}
      {policy.isError && <div className="panel-body"><StateNotice variant="error" /></div>}
      {policy.data && (
        <div className="domain-list" data-testid="domain-list">
          {domains.length === 0 && (
            <div className="domain-open-notice" data-testid="domain-open-notice"><ShieldAlert size={16} /><div><strong>Any Google account can currently sign in.</strong><span>Add your SIH team domain to restrict the console. Your own domain ({user?.email.split("@")[1]}) should be first so you are never locked out.</span></div></div>
          )}
          {domains.map((item) => (
            <div key={item} className="domain-row" data-testid={`domain-row-${item}`}>
              <ShieldCheck size={15} />
              <strong>{item}</strong>
              {item === user?.email.split("@")[1] && <span className="session-current-tag">YOUR DOMAIN</span>}
              <button type="button" className="session-revoke" aria-label={`Remove ${item}`} disabled={removeDomain.isPending} onClick={() => removeDomain.mutate(item)} data-testid={`domain-remove-${item}`}><Trash2 size={13} />Remove</button>
            </div>
          ))}
        </div>
      )}
      <div className="registry-footer"><KeyRound size={13} /> Policy updated {formatUtc(policy.data?.updated_at)} by {policy.data?.updated_by ?? "—"}. Removing a domain signs out every operator on it.</div>
    </Panel>
  );
}
