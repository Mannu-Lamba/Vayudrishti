export type Role = "analyst" | "admin";

export interface AuthUser {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  role: Role;
}

// Mirrors backend/models/auth.py::SessionInfo
export interface SessionInfo {
  session_id: string;
  browser: string;
  os: string;
  ip?: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export interface SessionListResponse {
  sessions: SessionInfo[];
}

export interface RevokeOthersResponse {
  revoked: number;
}

// Mirrors backend/models/auth.py::AccessPolicy
export interface AccessPolicy {
  allowed_domains: string[];
  open_access: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
}

// Mirrors backend/models/auth.py::ManagedUser
export interface ManagedUser {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  role: Role;
  created_at?: string | null;
  last_login_at?: string | null;
  active_sessions: number;
}
