import { ArrowLeft, ShieldX } from "lucide-react";
import BrandMark from "@/components/layout/BrandMark";
import { beginGoogleLogin } from "@/services/auth";

export default function AccessDenied({ message }: { message: string }) {
  return (
    <main className="auth-screen" data-testid="access-denied-screen">
      <div className="auth-login-panel">
        <div className="auth-brand"><BrandMark /><div><strong>VayuDrishti</strong><small>Cyclone intelligence · SIH 2026</small></div></div>
        <div className="auth-kicker auth-kicker-danger"><span /> ACCESS DENIED · DOMAIN POLICY</div>
        <h1>This account is<br /><em>outside the team perimeter.</em></h1>
        <p className="auth-description" data-testid="access-denied-message">{message}</p>
        <div className="auth-notice auth-notice-danger"><ShieldX size={14} /><span>Only approved SIH team email domains can enter the operations console. The attempt has been recorded in the audit trail.</span></div>
        <button type="button" className="google-login-button" onClick={beginGoogleLogin} data-testid="access-denied-retry-button"><ArrowLeft size={15} /><span>Try a different Google account</span></button>
      </div>
      <div className="auth-footer">VAYUDRISHTI / SIH 2026 <span>AUTH GATEWAY · RESTRICTED</span></div>
    </main>
  );
}
