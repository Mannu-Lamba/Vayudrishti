from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


AnalystMode = Literal["briefing", "methodology", "qa"]


class AnalystRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    mode: AnalystMode
    question: str | None = Field(default=None, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)


class AnalystMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: Literal["user", "assistant"]
    mode: AnalystMode
    content: str
    user_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))