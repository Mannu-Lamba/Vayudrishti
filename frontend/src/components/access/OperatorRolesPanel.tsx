import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserCog, UserRound } from "lucide-react";
import { toast } from "sonner";
import Panel from "@/components/common/Panel";
import StateNotice from "@/components/common/StateNotice";
import { errorDetail } from "@/lib/errors";
import { useAuth } from "@/lib/auth";
import { formatRelative } from "@/lib/time";
import { getManagedUsers, updateUserRole } from "@/services/access";
import type { ManagedUser, Role } from "@/types/auth";

/** Operator roles section: promote/demote analysts and administrators. */
export default function OperatorRolesPanel() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["managed-users"], queryFn: getManagedUsers });

  const changeRole = useMutation({
    mutationFn: ({ target, role }: { target: ManagedUser; role: Role }) => updateUserRole(target.user_id, role),
    onSuccess: (updated) => { void queryClient.invalidateQueries({ queryKey: ["managed-users"] }); void queryClient.invalidateQueries({ queryKey: ["audit"] }); toast.success(`${updated.name} is now ${updated.role === "admin" ? "an administrator" : "an analyst"}`); },
    onError: (error) => toast.error(errorDetail(error, "Could not change role")),
  });

  return (
    <Panel eyebrow="OPERATOR ROLES" title="Registered operators" data-testid="operators-panel">
      {users.isLoading && <div className="panel-body"><StateNotice variant="loading" /></div>}
      {users.isError && <div className="panel-body"><StateNotice variant="error" /></div>}
      {users.data && (
        <div className="operator-list" data-testid="operator-list">
          {users.data.map((operator) => {
            const isSelf = operator.user_id === user?.user_id;
            return (
              <div key={operator.user_id} className="operator-row" data-testid={`operator-row-${operator.user_id}`}>
                <div className="operator-avatar">{operator.picture ? <img src={operator.picture} alt="" /> : <UserRound size={15} />}</div>
                <div className="session-copy">
                  <strong>{operator.name} {isSelf && <span className="session-current-tag">YOU</span>}</strong>
                  <span>{operator.email} · {operator.active_sessions} active session{operator.active_sessions === 1 ? "" : "s"} · last login {formatRelative(operator.last_login_at)}</span>
                </div>
                <span className={`role-badge role-badge-${operator.role}`} data-testid={`operator-role-${operator.user_id}`}>{operator.role === "admin" ? <UserCog size={11} /> : <UserRound size={11} />}{operator.role.toUpperCase()}</span>
                <select className="role-select" value={operator.role} disabled={isSelf || changeRole.isPending} aria-label={`Role for ${operator.email}`} onChange={(event) => changeRole.mutate({ target: operator, role: event.target.value as Role })} data-testid={`operator-role-select-${operator.user_id}`}>
                  <option value="analyst">Analyst</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
            );
          })}
        </div>
      )}
      <div className="registry-footer"><UserCog size={13} /> Analysts get the operations console, Session Center and their own audit trail. Administrators add access control and the all-operator audit view.</div>
    </Panel>
  );
}
