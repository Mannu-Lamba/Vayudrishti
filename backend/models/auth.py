from datetime import datetime, timezone
from typing import Literal
import re
import uuid

from pydantic import BaseModel, Field, field_validator


Role = Literal["analyst", "admin"]
DOMAIN_PATTERN = re.compile(r"^(?=.{3,253}$)([a-z0-9-]+\.)+[a-z]{2,}$")


def ensure_utc(value: datetime) -> datetime:
    """Motor returns naive UTC datetimes; make them explicit so JSON carries a timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AuthUser(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str | None = None
    role: Role = "analyst"


class AuthSessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=500)


class EmergentSessionData(BaseModel):
    id: str
    email: str
    name: str
    picture: str | None = None
    session_token: str


class SessionInfo(BaseModel):
    session_id: str
    browser: str
    os: str
    ip: str | None = None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = False

    _utc = field_validator("created_at", "last_seen_at", "expires_at")(ensure_utc)


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]


class RevokeOthersResponse(BaseModel):
    revoked: int


class AccessPolicy(BaseModel):
    allowed_domains: list[str]
    open_access: bool
    updated_at: datetime | None = None
    updated_by: str | None = None

    @field_validator("updated_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value else None


class DomainRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=253)

    @field_validator("domain")
    @classmethod
    def _normalise(cls, value: str) -> str:
        domain = value.strip().lower().lstrip("@")
        if not DOMAIN_PATTERN.match(domain):
            raise ValueError("Enter a valid domain such as sih-team.ac.in")
        return domain


class ManagedUser(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str | None = None
    role: Role
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    active_sessions: int = 0

    @field_validator("created_at", "last_login_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value else None


class RoleUpdateRequest(BaseModel):
    role: Role


def new_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:16]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
