import { LoaderCircle, Radar } from "lucide-react";

export default function AuthLoading({ callback = false }: { callback?: boolean }) {
  return <div className="auth-screen" data-testid={callback ? "auth-callback-loading" : "auth-loading"}><div className="auth-loading-content"><div className="auth-loading-mark"><Radar size={30} /></div><div className="auth-loading-title">VAYUDRISHTI</div><div className="auth-loading-copy"><LoaderCircle size={14} className="auth-spinner" />{callback ? "Establishing secure operator session" : "Verifying operator session"}</div></div></div>;
}