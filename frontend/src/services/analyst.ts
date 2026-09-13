import { apiGet, apiStream } from "@/services/apiClient";
import type { AnalystMessage, AnalystRequest, AnalystStreamEvent } from "@/types/analyst";

const SESSION_STORAGE_KEY = "vayudrishti-analyst-session";

export function getAnalystSessionId(): string {
  const existing = localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem(SESSION_STORAGE_KEY, id);
  return id;
}

export function getAnalystHistory(sessionId: string): Promise<AnalystMessage[]> {
  return apiGet<AnalystMessage[]>(`/analyst/history/${sessionId}`);
}

export async function streamAnalystResponse(request: AnalystRequest, onDelta: (content: string) => void): Promise<AnalystMessage> {
  const stream = await apiStream("/analyst/stream", request);
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: AnalystMessage | undefined;
  let streamError: string | undefined;
  const consume = (block: string) => {
    const eventLine = block.split("\n").find((line) => line.startsWith("event: "));
    const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
    if (!dataLine) return;
    const data = JSON.parse(dataLine.slice(6)) as AnalystStreamEvent;
    if (eventLine?.trim() === "event: delta" && data.content) onDelta(data.content);
    if (eventLine?.trim() === "event: done" && data.content && data.message_id) completed = { id: data.message_id, session_id: request.session_id, role: "assistant", mode: request.mode, content: data.content, created_at: new Date().toISOString() };
    if (eventLine?.trim() === "event: error") streamError = data.message ?? "Claude analyst unavailable";
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    blocks.forEach(consume);
    if (done) break;
  }
  if (streamError) throw new Error(streamError);
  if (!completed) throw new Error("Claude ended without a complete response");
  return completed;
}