"""Audit trail writer. Every important operator action lands in `audit_events` through record_audit()."""

import logging
from typing import Any

from fastapi import Request

from lib.db import db
from models.audit import AuditEvent
from models.auth import AuthUser


logger = logging.getLogger(__name__)


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def record_audit(
    action: str,
    *,
    actor: AuthUser | None = None,
    request: Request | None = None,
    actor_email: str | None = None,
    actor_name: str | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor.user_id if actor else None,
        actor_email=actor.email if actor else (actor_email or "unknown"),
        actor_name=actor.name if actor else (actor_name or "Unknown identity"),
        actor_role=actor.role if actor else "guest",
        action=action,
        target=target,
        details=details or {},
        ip=client_ip(request),
    )
    try:
        await db.audit_events.insert_one(event.model_dump())
    except Exception:  # an audit write must never break the operator action itself
        logger.exception("audit write failed for %s", action)
    return event
