"""Integration tests for /chat endpoints.

These tests mock the Ollama LLM so no running Ollama instance is required.
To run against a real Ollama instance, remove the mock fixtures and ensure
Ollama is running with `gemma4:e2b` available.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage


def make_mock_llm(reply: str = "Hello from mock!", thinking: str | None = None) -> MagicMock:
    msg = AIMessage(content=reply)
    if thinking:
        msg.additional_kwargs["reasoning_content"] = thinking
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=msg)
    return llm


@pytest.fixture(autouse=True)
def mock_registry(monkeypatch):
    """Replace ModelRegistry.get_llm so no real Ollama calls happen."""
    mock_llm = make_mock_llm()

    async def fake_get_llm(self, model_name: str):
        return mock_llm

    monkeypatch.setattr("app.model_registry.ModelRegistry.get_llm", fake_get_llm)
    return mock_llm


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_new_chat_creates_session(client: AsyncClient):
    resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "chat_id" in data
    assert data["model"] == "gemma4:e2b"
    assert data["reply"] == "Hello from mock!"
    assert len(data["messages"]) == 2  # human + assistant


@pytest.mark.asyncio
async def test_continue_existing_session(client: AsyncClient):
    # Create session
    r1 = await client.post("/chat", json={"message": "first"})
    chat_id = r1.json()["chat_id"]

    # Continue it
    r2 = await client.post("/chat", json={"message": "second", "chat_id": chat_id})
    assert r2.status_code == 200
    assert r2.json()["chat_id"] == chat_id
    assert len(r2.json()["messages"]) == 4  # 2 turns × 2 messages


@pytest.mark.asyncio
async def test_invalid_chat_id_returns_404(client: AsyncClient):
    resp = await client.post("/chat", json={"message": "hi", "chat_id": "does-not-exist"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_model_returns_400(client: AsyncClient):
    resp = await client.post("/chat", json={"message": "hi", "model": "not-a-real-model"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_chat_history(client: AsyncClient):
    r = await client.post("/chat", json={"message": "tell me something"})
    chat_id = r.json()["chat_id"]

    hist = await client.get(f"/chat/{chat_id}")
    assert hist.status_code == 200
    data = hist.json()
    assert data["chat_id"] == chat_id
    assert len(data["messages"]) == 2


@pytest.mark.asyncio
async def test_get_missing_chat_returns_404(client: AsyncClient):
    resp = await client.get("/chat/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_chat(client: AsyncClient):
    r = await client.post("/chat", json={"message": "delete me"})
    chat_id = r.json()["chat_id"]

    del_resp = await client.delete(f"/chat/{chat_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # Subsequent get should 404
    assert (await client.get(f"/chat/{chat_id}")).status_code == 404


@pytest.mark.asyncio
async def test_delete_missing_chat_returns_404(client: AsyncClient):
    resp = await client.delete("/chat/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_thinking_mode_included_in_response(client: AsyncClient, monkeypatch):
    thinking_llm = make_mock_llm(reply="The answer is 42.", thinking="Let me reason...")

    async def fake_get_llm_thinking(self, model_name: str):
        return thinking_llm

    monkeypatch.setattr("app.model_registry.ModelRegistry.get_llm", fake_get_llm_thinking)

    resp = await client.post("/chat", json={"message": "think hard", "mode": "thinking"})
    assert resp.status_code == 200
    assert resp.json()["thinking"] == "Let me reason..."


@pytest.mark.asyncio
async def test_nothinking_mode_no_thinking_field(client: AsyncClient):
    resp = await client.post("/chat", json={"message": "quick answer", "mode": "nothinking"})
    assert resp.status_code == 200
    assert resp.json()["thinking"] is None
