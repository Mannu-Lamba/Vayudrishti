import { KeyRound } from "lucide-react";
import DomainAllowlistPanel from "@/components/access/DomainAllowlistPanel";
import OperatorRolesPanel from "@/components/access/OperatorRolesPanel";
import LockoutGuardPanel from "@/components/access/LockoutGuardPanel";

export default function AccessControl() {
  return (
    <div className="page-stack" data-testid="access-control-page">
      <div className="page-intro-row">
        <div>
          <div className="section-kicker"><KeyRound size={13} /> ADMINISTRATION / ACCESS CONTROL</div>
          <h2 className="page-heading">Access control</h2>
          <p className="page-subheading">Decide which team domains may enter the console, which operators carry administrator tooling, and the safeguards that keep any change from locking everyone out.</p>
        </div>
      </div>

      <div className="access-grid">
        <DomainAllowlistPanel />
        <OperatorRolesPanel />
      </div>

      <LockoutGuardPanel />
    </div>
  );
}
