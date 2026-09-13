import logging
import os
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from lib.access import email_domain, is_email_allowed
from lib.audit import client_ip, record_audit
from lib.db import db
from models.auth import AuthSessionRequest, AuthUser, EmergentSessionData, Role, ensure_utc, new_session_id, new_user_id, utc_now


logger = logging.getLogger(__name__)
router = APIRouter()
SESSION_COOKIE = "session_token"
SESSION_DAYS = 7
SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
TOUCH_INTERVAL = timedelta(seconds=60)


def session_token_from(request: Request) -> str | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip() or None
    return None


# Ordered (label, markers) pairs — first marker found wins, so keep the more specific
# engines (Edge, Opera) ahead of the Chrome/Safari tokens they also carry.
_BROWSER_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Edge", ("edg/",)),
    ("Opera", ("opr/", "opera")),
    ("Chrome", ("chrome/", "crios/")),
    ("Firefox", ("firefox/", "fxios/")),
    ("Safari", ("safari/",)),
    ("API client", ("curl/", "python", "httpx")),
)

_PLATFORM_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Windows", ("windows",)),
    ("Android", ("android",)),
    ("iOS", ("iphone", "ipad")),
    ("macOS", ("mac os", "macintosh")),
    ("ChromeOS", ("cros",)),
    ("Linux", ("linux",)),
)


def _match_marker(ua: str, table: tuple[tuple[str, tuple[str, ...]], ...], fallback: str) -> str:
    for label, markers in table:
        if any(marker in ua for marker in markers):
            return label
    return fallback


def parse_user_agent(user_agent: str) -> tuple[str, str]:
    ua = user_agent.lower()
    return (
        _match_marker(ua, _BROWSER_MARKERS, "Unknown browser"),
        _match_marker(ua, _PLATFORM_MARKERS, "Unknown OS"),
    )


def _admin_emails() -> set[str]:
    return {part.strip().lower() for part in os.environ.get("ADMIN_EMAILS", "").split(",") if part.strip()}


async def resolve_role(email: str, stored_role: str | None) -> Role:
    """Stored role wins; otherwise ADMIN_EMAILS, then the first real operator bootstraps as admin."""
    if stored_role in ("analyst", "admin"):
        return stored_role  # type: ignore[return-value]
    if email.lower() in _admin_emails():
        return "admin"
    existing_admins = await db.users.count_documents({"role": "admin", "is_test": {"$ne": True}})
    return "admin" if existing_admins == 0 else "analyst"


async def get_current_user(request: Request) -> AuthUser:
    token = session_token_from(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session not found")
    now = utc_now()
    if ensure_utc(session["expires_at"]) < now:
        await db.user_sessions.delete_one({"session_token": token})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not await is_email_allowed(user["email"]):
        await db.user_sessions.delete_many({"user_id": user["user_id"]})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access for {email_domain(user['email'])} has been revoked by an administrator")

    role = await resolve_role(user["email"], user.get("role"))
    if user.get("role") != role:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": role}})

    last_seen = session.get("last_seen_at")
    if last_seen is None or now - ensure_utc(last_seen) > TOUCH_INTERVAL:
        await db.user_sessions.update_one({"session_token": token}, {"$set": {"last_seen_at": now}})

    request.state.session_token = token
    return AuthUser(user_id=user["user_id"], email=user["email"], name=user["name"], picture=user.get("picture"), role=role)


def require_admin(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return current_user


@router.post("/session", response_model=AuthUser)
async def exchange_google_session(payload: AuthSessionRequest, request: Request, response: Response):
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            upstream = await client.get(SESSION_DATA_URL, headers={"X-Session-ID": payload.session_id})
        upstream.raise_for_status()
        session_data = EmergentSessionData.model_validate(upstream.json())
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Emergent auth exchange failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in could not be completed") from exc

    domain = email_domain(session_data.email)
    if not await is_email_allowed(session_data.email):
        await record_audit("auth.sign_in_denied", request=request, actor_email=session_data.email, actor_name=session_data.name, target=domain, details={"reason": "domain_not_approved"})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{domain} is not an approved team domain. Ask a VayuDrishti administrator to add it.")

    now = utc_now()
    existing = await db.users.find_one({"email": session_data.email}, {"_id": 0})
    role = await resolve_role(session_data.email, existing.get("role") if existing else None)
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": session_data.name, "picture": session_data.picture, "role": role, "updated_at": now, "last_login_at": now}})
    else:
        user_id = new_user_id()
        await db.users.insert_one({"user_id": user_id, "email": session_data.email, "name": session_data.name, "picture": session_data.picture, "role": role, "created_at": now, "updated_at": now, "last_login_at": now})

    browser, platform = parse_user_agent(request.headers.get("user-agent", ""))
    await db.user_sessions.insert_one({
        "session_id": new_session_id(), "user_id": user_id, "session_token": session_data.session_token,
        "browser": browser, "os": platform, "ip": client_ip(request),
        "created_at": now, "last_seen_at": now, "expires_at": now + timedelta(days=SESSION_DAYS),
    })
    user = AuthUser(user_id=user_id, email=session_data.email, name=session_data.name, picture=session_data.picture, role=role)
    await record_audit("auth.sign_in", actor=user, request=request, target=domain, details={"browser": browser, "os": platform})
    response.set_cookie(SESSION_COOKIE, session_data.session_token, max_age=SESSION_DAYS * 24 * 60 * 60, httponly=True, secure=True, samesite="none", path="/")
    return user


@router.get("/me", response_model=AuthUser)
async def get_me(current_user: AuthUser = Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    token = session_token_from(request)
    if token:
        try:
            user = await get_current_user(request)
            await record_audit("auth.sign_out", actor=user, request=request)
        except HTTPException:
            pass
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="none")
