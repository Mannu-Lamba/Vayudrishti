export type AnalystMode = "briefing" | "methodology" | "qa";

export interface AnalystRequest {
  session_id: string;
  mode: AnalystMode;
  question?: string;
  context: Record<string, unknown>;
}

export interface AnalystMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  mode: AnalystMode;
  content: string;
  user_id?: string | null;
  created_at: string;
}

export interface AnalystStreamEvent {
  content?: string;
  message?: string;
  message_id?: string;
}