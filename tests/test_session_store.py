import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.session_store import ChatSession, SessionStore
from datetime import datetime, timezone


def make_session(n_turns: int, with_system: bool = False) -> ChatSession:
    messages = []
    if with_system:
        messages.append(SystemMessage(content="You are helpful."))
    for i in range(n_turns):
        messages.append(HumanMessage(content=f"q{i}"))
        messages.append(AIMessage(content=f"a{i}"))
    return ChatSession(
        chat_id="test",
        model="gemma4:e2b",
        created_at=datetime.now(tz=timezone.utc),
        messages=messages,
    )


def test_truncation_no_overflow():
    session = make_session(5)
    result = session.truncated_messages(20)
    assert len(result) == 10  # 5 turns × 2 messages


def test_truncation_at_limit():
    session = make_session(15)
    result = session.truncated_messages(20)
    assert len(result) == 20


def test_truncation_overflow():
    session = make_session(15)
    result = session.truncated_messages(10)
    assert len(result) == 10
    # Should be the last 10 messages
    assert result[0].content == "q10"


def test_system_message_always_preserved():
    session = make_session(15, with_system=True)
    result = session.truncated_messages(10)
    # First message is the system prompt
    assert isinstance(result[0], SystemMessage)
    # Total = 1 system + 9 history
    assert len(result) == 10


def test_empty_session():
    session = make_session(0)
    assert session.truncated_messages(20) == []


@pytest.mark.asyncio
async def test_store_create_and_get():
    store = SessionStore()
    session = await store.create("abc", "gemma4:e2b")
    assert session.chat_id == "abc"

    fetched = await store.get("abc")
    assert fetched is not None
    assert fetched.chat_id == "abc"


@pytest.mark.asyncio
async def test_store_get_missing():
    store = SessionStore()
    assert await store.get("nonexistent") is None


@pytest.mark.asyncio
async def test_store_delete():
    store = SessionStore()
    await store.create("del-me", "gemma4:e2b")
    deleted = await store.delete("del-me")
    assert deleted is True
    assert await store.get("del-me") is None


@pytest.mark.asyncio
async def test_store_delete_missing():
    store = SessionStore()
    deleted = await store.delete("nope")
    assert deleted is False


@pytest.mark.asyncio
async def test_store_append_messages():
    store = SessionStore()
    await store.create("chat1", "gemma4:e2b")
    await store.append_messages("chat1", [HumanMessage(content="hi"), AIMessage(content="hello")])
    session = await store.get("chat1")
    assert len(session.messages) == 2
