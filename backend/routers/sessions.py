from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from lib.audit import record_audit
from lib.db import db
from models.auth import AuthUser, RevokeOthersResponse, SessionInfo, SessionListResponse, utc_now
from routers.auth import SESSION_COOKIE, get_current_user, session_token_from


router = APIRouter()


def _to_info(document: dict, current_token: str | None) -> SessionInfo:
    now = utc_now()
    return SessionInfo(
        session_id=document.get("session_id") or f"legacy_{document['session_token'][-8:]}",
        browser=document.get("browser", "Unknown browser"),
        os=document.get("os", "Unknown OS"),
        ip=document.get("ip"),
        created_at=document.get("created_at", now),
        last_seen_at=document.get("last_seen_at") or document.get("created_at", now),
        expires_at=document["expires_at"],
        current=document["session_token"] == current_token,
    )


async def _own_sessions(user_id: str) -> list[dict]:
    return await db.user_sessions.find({"user_id": user_id}, {"_id": 0}).to_list(100)


@router.get("", response_model=SessionListResponse)
async def list_sessions(request: Request, current_user: AuthUser = Depends(get_current_user)):
    token = session_token_from(request)
    sessions = [_to_info(document, token) for document in await _own_sessions(current_user.user_id)]
    sessions.sort(key=lambda item: (not item.current, -item.last_seen_at.timestamp()))
    return SessionListResponse(sessions=sessions)


@router.post("/revoke-others", response_model=RevokeOthersResponse)
async def revoke_other_sessions(request: Request, current_user: AuthUser = Depends(get_current_user)):
    token = session_token_from(request)
    result = await db.user_sessions.delete_many({"user_id": current_user.user_id, "session_token": {"$ne": token}})
    await record_audit("session.revoked_others", actor=current_user, request=request, details={"revoked": result.deleted_count})
    return RevokeOthersResponse(revoked=result.deleted_count)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: str, request: Request, response: Response, current_user: AuthUser = Depends(get_current_user)):
    token = session_token_from(request)
    target = next((document for document in await _own_sessions(current_user.user_id) if _to_info(document, token).session_id == session_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await db.user_sessions.delete_one({"session_token": target["session_token"]})
    is_current = target["session_token"] == token
    await record_audit("session.revoked", actor=current_user, request=request, target=session_id, details={"browser": target.get("browser"), "os": target.get("os"), "current": is_current})
    if is_current:
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="none")
