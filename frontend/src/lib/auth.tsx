import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/services/apiClient";
import { getCurrentUser } from "@/services/auth";
import type { AuthUser } from "@/types/auth";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAdmin: boolean;
  deniedMessage: string | null;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function deniedFrom(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 403) return null;
  const detail = (error.body as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : "Your email domain is no longer approved for this console.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery({ queryKey: ["auth-user"], queryFn: getCurrentUser, retry: false, staleTime: 60_000 });
  const value = useMemo(
    () => ({ user: query.data ?? null, isLoading: query.isLoading, isAdmin: query.data?.role === "admin", deniedMessage: deniedFrom(query.error) }),
    [query.data, query.isLoading, query.error],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
