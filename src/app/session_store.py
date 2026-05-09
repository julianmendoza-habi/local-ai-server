import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

import asyncpg
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def _role_of(msg: BaseMessage) -> str:
    if isinstance(msg, HumanMessage):
        return "human"
    if isinstance(msg, AIMessage):
        return "assistant"
    if isinstance(msg, SystemMessage):
        return "system"
    return "unknown"


def _message_from_row(row: asyncpg.Record) -> BaseMessage:
    role, content, thinking = row["role"], row["content"], row["thinking"]
    if role == "human":
        return HumanMessage(content=content)
    if role == "assistant":
        kwargs = {"reasoning_content": thinking} if thinking else {}
        return AIMessage(content=content, additional_kwargs=kwargs)
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


@dataclass
class ChatSession:
    chat_id: str
    model: str
    created_at: datetime
    messages: list[BaseMessage] = field(default_factory=list)

    def truncated_messages(self, max_count: int) -> list[BaseMessage]:
        """Sliding-window context. System prompt (if first) is always preserved."""
        if not self.messages:
            return []
        if isinstance(self.messages[0], SystemMessage):
            tail = self.messages[1:][-(max_count - 1):]
            return [self.messages[0]] + tail
        return self.messages[-max_count:]


class AbstractSessionStore(Protocol):
    async def create(self, chat_id: str, model: str, user_id: UUID | None = None) -> ChatSession: ...
    async def get(self, chat_id: str) -> ChatSession | None: ...
    async def append_messages(self, chat_id: str, messages: list[BaseMessage]) -> None: ...
    async def delete(self, chat_id: str) -> bool: ...


class SessionStore:
    """Async-safe in-memory store. Use when DATABASE_URL is not configured."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, chat_id: str, model: str, user_id: UUID | None = None) -> ChatSession:
        session = ChatSession(
            chat_id=chat_id,
            model=model,
            created_at=datetime.now(tz=timezone.utc),
        )
        async with self._lock:
            self._sessions[chat_id] = session
        return session

    async def get(self, chat_id: str) -> ChatSession | None:
        async with self._lock:
            return self._sessions.get(chat_id)

    async def append_messages(self, chat_id: str, messages: list[BaseMessage]) -> None:
        async with self._lock:
            session = self._sessions.get(chat_id)
            if session is not None:
                session.messages.extend(messages)

    async def delete(self, chat_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(chat_id, None) is not None


class PostgresSessionStore:
    """PostgreSQL-backed store via asyncpg connection pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, chat_id: str, model: str, user_id: UUID | None = None) -> ChatSession:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO chat_sessions (id, model, user_id) VALUES ($1, $2, $3) RETURNING created_at",
                chat_id,
                model,
                user_id,
            )
        return ChatSession(chat_id=chat_id, model=model, created_at=row["created_at"])

    async def get(self, chat_id: str) -> ChatSession | None:
        async with self._pool.acquire() as conn:
            session_row = await conn.fetchrow(
                "SELECT id, model, created_at FROM chat_sessions WHERE id = $1",
                chat_id,
            )
            if session_row is None:
                return None
            message_rows = await conn.fetch(
                "SELECT role, content, thinking FROM messages WHERE chat_id = $1 ORDER BY id ASC",
                chat_id,
            )
        return ChatSession(
            chat_id=session_row["id"],
            model=session_row["model"],
            created_at=session_row["created_at"],
            messages=[_message_from_row(r) for r in message_rows],
        )

    async def append_messages(self, chat_id: str, messages: list[BaseMessage]) -> None:
        rows = [
            (
                chat_id,
                _role_of(msg),
                str(msg.content),
                msg.additional_kwargs.get("reasoning_content") if isinstance(msg, AIMessage) else None,
            )
            for msg in messages
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO messages (chat_id, role, content, thinking) VALUES ($1, $2, $3, $4)",
                rows,
            )

    async def delete(self, chat_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM chat_sessions WHERE id = $1", chat_id)
        return result != "DELETE 0"
