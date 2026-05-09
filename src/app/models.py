from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    chat_id: str | None = None
    model: str | None = None
    mode: Literal["thinking", "nothinking"] | None = None


class MessageRecord(BaseModel):
    role: str
    content: str
    thinking: str | None = None


class ChatResponse(BaseModel):
    chat_id: str
    model: str
    reply: str
    thinking: str | None = None
    messages: list[MessageRecord]


class ChatHistoryResponse(BaseModel):
    chat_id: str
    model: str
    created_at: datetime
    messages: list[MessageRecord]


class DeleteResponse(BaseModel):
    deleted: bool
    chat_id: str


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenUser(BaseModel):
    """Decoded JWT payload — attached to every authenticated request."""
    id: str
    email: str
    is_admin: bool


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AllowedEmailIn(BaseModel):
    email: str
    note: str | None = None


class AllowedEmailOut(BaseModel):
    email: str
    note: str | None
    added_at: datetime
