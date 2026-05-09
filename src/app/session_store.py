import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def _role_of(msg: BaseMessage) -> str:
    if isinstance(msg, HumanMessage):
        return "human"
    if isinstance(msg, AIMessage):
        return "assistant"
    if isinstance(msg, SystemMessage):
        return "system"
    return "unknown"


@dataclass
class ChatSession:
    chat_id: str
    model: str
    created_at: datetime
    messages: list[BaseMessage] = field(default_factory=list)

    def truncated_messages(self, max_count: int) -> list[BaseMessage]:
        """Return at most max_count messages using a sliding window.

        If the first message is a SystemMessage it is always preserved and
        does not count toward the window — so effective history is max_count-1
        turns plus the system prompt.
        """
        if not self.messages:
            return []
        if isinstance(self.messages[0], SystemMessage):
            tail = self.messages[1:][-(max_count - 1):]
            return [self.messages[0]] + tail
        return self.messages[-max_count:]


class SessionStore:
    """Async-safe in-memory session store.

    All public methods are async so a future implementation can swap the
    backing store to a database without changing call sites.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, chat_id: str, model: str) -> ChatSession:
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
