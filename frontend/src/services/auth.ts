import { apiGet, apiPost } from "@/services/apiClient";
import { beginSession } from "@/lib/session";
import type { AuthUser } from "@/types/auth";

export function getCurrentUser(): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me");
}

export async function exchangeAuthSession(sessionId: string): Promise<AuthUser> {
  const user = await apiPost<AuthUser>("/auth/session", { session_id: sessionId });
  beginSession();
  return user;
}

export function beginGoogleLogin(): void {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = `${window.location.origin}/`;
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
}