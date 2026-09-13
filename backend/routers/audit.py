from fastapi import APIRouter, Depends, Query, Request

from lib.audit import record_audit
from lib.db import db
from models.audit import AuditEvent, AuditEventCreate, AuditListResponse, AuditScope
from models.auth import AuthUser
from routers.auth import get_current_user


router = APIRouter()


@router.post("/events", response_model=AuditEvent, status_code=201)
async def create_client_event(payload: AuditEventCreate, request: Request, current_user: AuthUser = Depends(get_current_user)):
    return await record_audit(payload.action, actor=current_user, request=request, target=payload.target, details=payload.details)


@router.get("/events", response_model=AuditListResponse)
async def list_events(
    scope: AuditScope = Query("mine"),
    action: str | None = Query(None, max_length=60),
    limit: int = Query(100, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
):
    # Analysts only ever see their own trail; administrators may widen to every operator.
    effective_scope: AuditScope = "all" if scope == "all" and current_user.role == "admin" else "mine"
    query: dict = {} if effective_scope == "all" else {"actor_user_id": current_user.user_id}
    if action:
        query["action"] = action
    total = await db.audit_events.count_documents(query)
    documents = await db.audit_events.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return AuditListResponse(events=[AuditEvent(**document) for document in documents], scope=effective_scope, total=total)
