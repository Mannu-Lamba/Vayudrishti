import { useEffect, useState } from "react";
import { AlertTriangle, BrainCircuit, FileText, LoaderCircle, MessageCircleQuestion, RefreshCcw, Send, Sparkles, UserRound } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import Panel from "@/components/common/Panel";
import { getAnalystHistory, getAnalystSessionId, streamAnalystResponse } from "@/services/analyst";
import type { AnalystMessage, AnalystMode, AnalystRequest } from "@/types/analyst";

interface AnalystWorkspaceProps {
  context: Record<string, unknown>;
}

const modeMeta: Record<AnalystMode, { label: string; description: string; icon: typeof BrainCircuit }> = {
  briefing: { label: "AI briefing", description: "Read the current signal", icon: BrainCircuit },
  methodology: { label: "Methodology", description: "Explain the future pipeline", icon: FileText },
  qa: { label: "Ask analyst", description: "Ask about the current context", icon: MessageCircleQuestion },
};

const suggestions: Record<AnalystMode, string[]> = {
  briefing: ["Summarize the current storm signal", "What should an operator watch next?"],
  methodology: ["How will satellite data become a forecast?", "What does model confidence mean here?"],
  qa: ["Why is VD-001 high risk?", "What is the current movement and pressure?"],
};

function historyLabel(mode: AnalystMode): string {
  return mode === "briefing" ? "briefing" : mode === "methodology" ? "methodology note" : "operator question";
}

export default function AnalystWorkspace({ context }: AnalystWorkspaceProps) {
  const [mode, setMode] = useState<AnalystMode>("briefing");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<AnalystMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [lastRequest, setLastRequest] = useState<AnalystRequest>();
  const [sessionId] = useState(getAnalystSessionId);
  const historyQuery = useQuery({ queryKey: ["analyst-history", sessionId], queryFn: () => getAnalystHistory(sessionId), retry: false });

  useEffect(() => {
    if (historyQuery.data) setMessages(historyQuery.data);
  }, [historyQuery.data]);

  const submit = async (preset?: string) => {
    const question = (preset ?? draft).trim();
    if (mode === "qa" && !question) {
      setError("Enter a question for the analyst first.");
      return;
    }
    const request: AnalystRequest = { session_id: sessionId, mode, question: question || undefined, context };
    const userMessage: AnalystMessage = { id: `local-user-${Date.now()}`, session_id: sessionId, role: "user", mode, content: question || `Generate a ${historyLabel(mode)}.`, created_at: new Date().toISOString() };
    const assistantId = `local-assistant-${Date.now()}`;
    const assistantMessage: AnalystMessage = { id: assistantId, session_id: sessionId, role: "assistant", mode, content: "", created_at: new Date().toISOString() };
    setMessages((current) => [...current, userMessage, assistantMessage]);
    setDraft("");
    setError(undefined);
    setLoading(true);
    setLastRequest(request);
    try {
      await streamAnalystResponse(request, (content) => setMessages((current) => current.map((item) => item.id === assistantId ? { ...item, content: `${item.content}${content}` } : item)));
    } catch (caught) {
      setMessages((current) => current.filter((item) => item.id !== assistantId));
      setError(caught instanceof Error ? caught.message : "Claude analyst unavailable");
    } finally {
      setLoading(false);
    }
  };

  return <Panel className="analyst-workspace" eyebrow="OPTIONAL INTELLIGENCE LAYER" title="Claude analyst" action={<span className="mock-badge"><Sparkles size={12} /> CLAUDE / OPTIONAL</span>} data-testid="analyst-workspace">
    <div className="analyst-intro"><div className="analyst-intro-icon"><BrainCircuit size={20} /></div><div><strong>Ask the signal, not the interface.</strong><p>Claude can summarize the selected storm and forecast shown on this page, explain the methodology, or answer an operator question. The dashboard remains usable if the AI service is offline.</p></div></div>
    <div className="analyst-tabs" role="tablist" aria-label="Analyst modes">{(Object.keys(modeMeta) as AnalystMode[]).map((item) => { const meta = modeMeta[item]; const Icon = meta.icon; return <button type="button" role="tab" aria-selected={mode === item} className={mode === item ? "analyst-tab analyst-tab-active" : "analyst-tab"} onClick={() => { setMode(item); setError(undefined); }} data-testid={`analyst-mode-${item}-button`} key={item}><Icon size={15} /><span><strong>{meta.label}</strong><small>{meta.description}</small></span></button>; })}</div>
    <div className="analyst-message-list" data-testid="analyst-message-list">{messages.length === 0 ? <div className="analyst-empty"><Sparkles size={18} /><strong>Claude is ready for an optional readout</strong><span>Use a suggested prompt or write your own question below.</span><div className="analyst-suggestions">{suggestions[mode].map((suggestion, index) => <button type="button" key={suggestion} onClick={() => void submit(suggestion)} data-testid={`analyst-suggestion-${mode}-${index}`}>{suggestion}</button>)}</div></div> : messages.map((message) => <div className={`analyst-message analyst-message-${message.role}`} key={message.id} data-testid={`analyst-message-${message.role}`}><div className="analyst-message-avatar">{message.role === "assistant" ? <BrainCircuit size={14} /> : <UserRound size={14} />}</div><div><div className="analyst-message-meta">{message.role === "assistant" ? "CLAUDE ANALYST" : "OPERATOR"} · {historyLabel(message.mode).toUpperCase()}</div><p>{message.content || (loading ? "Reading the current signal…" : "")}</p></div></div>)}</div>
    {error && <div className="analyst-error" role="alert" data-testid="analyst-error"><AlertTriangle size={15} /><span>{error}</span>{lastRequest && <button type="button" onClick={() => void submit(lastRequest.question)} data-testid="analyst-retry-button"><RefreshCcw size={13} />Retry</button>}</div>}
    <div className="analyst-composer"><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={mode === "qa" ? "Ask about the current cyclone context…" : `Optional: refine the ${historyLabel(mode)} prompt…`} rows={2} disabled={loading} data-testid="analyst-question-input" /><button type="button" className="primary-action analyst-submit" onClick={() => void submit()} disabled={loading} data-testid="analyst-submit-button">{loading ? <LoaderCircle size={14} className="analyst-spinner" /> : <Send size={14} />}{loading ? "Reading…" : mode === "qa" ? "Ask Claude" : "Generate readout"}</button></div>
    <div className="analyst-footnote">AI output is advisory, not an official weather warning. Current model: Claude Sonnet 4.6.</div>
  </Panel>;
}