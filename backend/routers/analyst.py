import json
import logging
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage

from lib.audit import record_audit
from lib.db import db
from models.auth import AuthUser
from models.analyst import AnalystMessage, AnalystRequest
from routers.auth import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, payload: dict[str, str]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _system_prompt(mode: str) -> str:
    base = (
        "You are VayuDrishti Analyst, a careful tropical cyclone intelligence assistant. "
        "Use only the supplied operational context and clearly label uncertainty. "
        "Never invent live satellite readings, model scores, warnings, landfall certainty, or official advisories. "
        "This is a demonstration interface, not an emergency alert service. Keep responses concise, structured, and useful to a meteorological operator."
    )
    if mode == "methodology":
        return base + " Explain platform methodology in plain language, separating the Phase 1 mock boundary from future production services."
    if mode == "qa":
        return base + " Answer the operator's question directly, then add one short caveat if the mock context is insufficient."
    return base + " Produce a short briefing with: situation, signal, uncertainty, and operator note."


def _prompt(request: AnalystRequest, history: list[AnalystMessage]) -> str:
    context = json.dumps(request.context, separators=(",", ":"), default=str)
    recent = "\n".join(f"{message.role.upper()}: {message.content}" for message in history[-6:])
    if request.mode == "methodology":
        task = "Explain how VayuDrishti's observation → detection → classification → prediction pipeline should evolve from this frontend foundation."
    elif request.mode == "qa":
        task = request.question or "What should an operator understand from the current cyclone context?"
    else:
        task = "Generate a concise analyst briefing for the current monitored cyclone."
    return f"TASK: {task}\nCURRENT MOCK CONTEXT: {context}\nRECENT SESSION NOTES:\n{recent or '(none)'}"


async def _history(session_id: str, user_id: str) -> list[AnalystMessage]:
    documents = await db.analyst_messages.find({"session_id": session_id, "$or": [{"user_id": user_id}, {"user_id": {"$exists": False}}]}).sort("created_at", 1).to_list(20)
    return [AnalystMessage(**document) for document in documents]


@router.get("/history/{session_id}", response_model=list[AnalystMessage])
async def get_analyst_history(session_id: str, current_user: AuthUser = Depends(get_current_user)):
    return await _history(session_id, current_user.user_id)


@router.post("/stream")
async def stream_analyst_response(request: AnalystRequest, http_request: Request, current_user: AuthUser = Depends(get_current_user)):
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Claude analyst is not configured")

    await record_audit("analyst.requested", actor=current_user, request=http_request, target=request.mode, details={"session_id": request.session_id, "question": (request.question or "")[:160]})
    history = await _history(request.session_id, current_user.user_id)
    user_message = AnalystMessage(session_id=request.session_id, user_id=current_user.user_id, role="user", mode=request.mode, content=request.question or _prompt(request, history))
    await db.analyst_messages.insert_one(user_message.model_dump())
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    chat = LlmChat(api_key=api_key, session_id=f"vayudrishti-{request.session_id}", system_message=_system_prompt(request.mode)).with_model("anthropic", model)

    async def event_stream() -> AsyncIterator[str]:
        response_parts: list[str] = []
        try:
            async for event in chat.stream_message(UserMessage(text=_prompt(request, history))):
                if isinstance(event, TextDelta):
                    response_parts.append(event.content)
                    yield _sse("delta", {"content": event.content})
                elif isinstance(event, StreamDone):
                    break
            assistant_message = AnalystMessage(session_id=request.session_id, user_id=current_user.user_id, role="assistant", mode=request.mode, content="".join(response_parts))
            await db.analyst_messages.insert_one(assistant_message.model_dump())
            yield _sse("done", {"message_id": assistant_message.id, "content": assistant_message.content})
        except Exception:
            logger.exception("Claude analyst stream failed")
            yield _sse("error", {"message": "Claude is temporarily unavailable. Your mock console remains operational."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})