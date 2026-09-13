from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field, field_validator

from models.auth import ensure_utc, utc_now


# Actions the browser may record directly; everything else is written server-side only.
ClientAuditAction = Literal[
    "cyclone.selected",
    "satellite.layer_changed",
    "preferences.saved",
    "briefing.exported",
]

AuditScope = Literal["mine", "all"]


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    actor_user_id: str | None = None
    actor_email: str
    actor_name: str
    actor_role: str
    action: str
    target: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    _utc = field_validator("created_at")(ensure_utc)


class AuditEventCreate(BaseModel):
    action: ClientAuditAction
    target: str | None = Field(default=None, max_length=200)
    details: dict[str, Any] = Field(default_factory=dict)


class AuditListResponse(BaseModel):
    events: list[AuditEvent]
    scope: AuditScope
    total: int
