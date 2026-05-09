import asyncio
import logging
import time
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import settings
from app.exceptions import QueueOverloadError
from app.models import ChatHistoryResponse, ChatRequest, ChatResponse, DeleteResponse, MessageRecord
from app.model_registry import ModelRegistry
from app.session_store import ChatSession, SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Dependency injectors — implementations are wired up in main.py
# ---------------------------------------------------------------------------

_session_store: SessionStore | None = None
_model_registry: ModelRegistry | None = None


def get_session_store() -> SessionStore:
    assert _session_store is not None, "SessionStore not initialised"
    return _session_store


def get_model_registry() -> ModelRegistry:
    assert _model_registry is not None, "ModelRegistry not initialised"
    return _model_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODE_TO_REASONING: dict[str, bool] = {
    "thinking": True,
    "nothinking": False,
}


def _serialize_messages(messages: list[BaseMessage]) -> list[MessageRecord]:
    records: list[MessageRecord] = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        thinking = msg.additional_kwargs.get("reasoning_content") if isinstance(msg, AIMessage) else None
        records.append(MessageRecord(role=role, content=str(msg.content), thinking=thinking))
    return records


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    request: ChatRequest,
    store: SessionStore = Depends(get_session_store),
    registry: ModelRegistry = Depends(get_model_registry),
) -> ChatResponse:
    # Resolve session and model
    if request.chat_id:
        session = await store.get(request.chat_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Chat session '{request.chat_id}' not found")
        model_name = request.model or session.model
    else:
        model_name = request.model or settings.default_model
        session = await store.create(str(uuid4()), model_name)

    if model_name not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' is not in the allowed list")

    reasoning = _MODE_TO_REASONING.get(request.mode) if request.mode else None
    llm = await registry.get_llm(model_name)

    # Build context with sliding window
    human_msg = HumanMessage(content=request.message)
    context = session.truncated_messages(settings.max_messages_per_session) + [human_msg]

    # Acquire concurrency slot
    queue_enter = time.monotonic()
    try:
        await registry.acquire()
    except QueueOverloadError:
        raise HTTPException(
            status_code=503,
            headers={"Retry-After": "5"},
            detail="Server at capacity. Try again shortly.",
        )

    queue_wait_ms = (time.monotonic() - queue_enter) * 1000
    llm_start = time.monotonic()

    try:
        response: AIMessage = await asyncio.wait_for(
            llm.ainvoke(context, reasoning=reasoning),
            timeout=settings.request_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Model response timed out")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Ollama is not reachable. Is it running?")
    finally:
        registry.release()

    llm_ms = (time.monotonic() - llm_start) * 1000
    thinking = response.additional_kwargs.get("reasoning_content")

    logger.info(
        "chat_id=%s model=%s mode=%s queue_wait_ms=%.1f llm_time_ms=%.1f thinking=%s",
        session.chat_id,
        model_name,
        request.mode,
        queue_wait_ms,
        llm_ms,
        thinking is not None,
    )

    await store.append_messages(session.chat_id, [human_msg, response])

    return ChatResponse(
        chat_id=session.chat_id,
        model=model_name,
        reply=str(response.content),
        thinking=thinking,
        messages=_serialize_messages(
            session.truncated_messages(settings.max_messages_per_session)
        ),
    )


@router.get("/chat/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat(
    chat_id: str,
    store: SessionStore = Depends(get_session_store),
) -> ChatHistoryResponse:
    session = await store.get(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{chat_id}' not found")

    return ChatHistoryResponse(
        chat_id=session.chat_id,
        model=session.model,
        created_at=session.created_at,
        messages=_serialize_messages(session.messages),
    )


@router.delete("/chat/{chat_id}", response_model=DeleteResponse)
async def delete_chat(
    chat_id: str,
    store: SessionStore = Depends(get_session_store),
) -> DeleteResponse:
    deleted = await store.delete(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Chat session '{chat_id}' not found")
    return DeleteResponse(deleted=True, chat_id=chat_id)
