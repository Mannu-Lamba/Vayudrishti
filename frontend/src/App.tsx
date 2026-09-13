import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import AppLayout from "@/components/layout/AppLayout";
import AccessDenied from "@/components/auth/AccessDenied";
import AuthCallback from "@/components/auth/AuthCallback";
import AuthLoading from "@/components/auth/AuthLoading";
import LoginScreen from "@/components/auth/LoginScreen";
import { AuthProvider, useAuth } from "@/lib/auth";
import { PreferencesProvider } from "@/lib/preferences";
import Dashboard from "@/pages/Dashboard";
import Cyclones from "@/pages/Cyclones";
import Satellite from "@/pages/Satellite";
import Prediction from "@/pages/Prediction";
import History from "@/pages/History";
import About from "@/pages/About";
import Settings from "@/pages/Settings";
import Sessions from "@/pages/Sessions";
import Audit from "@/pages/Audit";
import AccessControl from "@/pages/AccessControl";

// Analysts who reach an admin URL are sent back to the dashboard rather than shown an error.
function AdminOnly({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  return isAdmin ? <>{children}</> : <Navigate to="/" replace />;
}

function ProtectedRoutes() {
  const { user, isLoading, deniedMessage } = useAuth();
  if (isLoading) return <AuthLoading />;
  if (deniedMessage) return <AccessDenied message={deniedMessage} />;
  if (!user) return <LoginScreen />;
  return (
    <PreferencesProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/" element={<Dashboard />} />
          <Route path="/cyclones" element={<Cyclones />} />
          <Route path="/satellite" element={<Satellite />} />
          <Route path="/prediction" element={<Prediction />} />
          <Route path="/history" element={<History />} />
          <Route path="/about" element={<About />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/admin" element={<AdminOnly><AccessControl /></AdminOnly>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </PreferencesProvider>
  );
}

export default function App() {
  const location = useLocation();
  const sessionId = new URLSearchParams(location.hash.replace(/^#/, "")).get("session_id");
  if (sessionId) return <AuthCallback sessionId={sessionId} />;
  return <AuthProvider><ProtectedRoutes /></AuthProvider>;
}
