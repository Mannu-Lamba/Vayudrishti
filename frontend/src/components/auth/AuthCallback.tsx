import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import AccessDenied from "@/components/auth/AccessDenied";
import AuthLoading from "@/components/auth/AuthLoading";
import LoginScreen from "@/components/auth/LoginScreen";
import { ApiError } from "@/services/apiClient";
import { exchangeAuthSession } from "@/services/auth";

type CallbackState = { kind: "pending" } | { kind: "denied"; message: string } | { kind: "failed" };

export default function AuthCallback({ sessionId }: { sessionId: string }) {
  const navigate = useNavigate();
  const processed = useRef(false);
  const [state, setState] = useState<CallbackState>({ kind: "pending" });
  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    void exchangeAuthSession(sessionId)
      .then(() => navigate("/", { replace: true }))
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 403) {
          const detail = (error.body as { detail?: unknown } | null)?.detail;
          setState({ kind: "denied", message: typeof detail === "string" ? detail : "Your email domain is not approved for this console." });
          return;
        }
        setState({ kind: "failed" });
      });
  }, [navigate, sessionId]);
  if (state.kind === "denied") return <AccessDenied message={state.message} />;
  if (state.kind === "failed") return <LoginScreen />;
  return <AuthLoading callback />;
}
