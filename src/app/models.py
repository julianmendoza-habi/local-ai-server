from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
