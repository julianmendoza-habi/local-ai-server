import json
import logging
from typing import AsyncIterator, Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from ollama import ResponseError as OllamaResponseError

from app.auth.dependencies import current_user
from app.config import settings
from app.exceptions import QueueOverloadError
from app.models import ChatRequest, TokenUser
from app.model_registry import ModelRegistry
from app.session_store import AbstractSessionStore, ChatSession
from app.routers.chat import get_model_registry, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])

_MODE_TO_REASONING: dict[str, bool] = {
    "thinking": True,
    "nothinking": False,
}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _streaming_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream", headers=_SSE_HEADERS)


async def _run_stream(
    session: ChatSession,
    message: str,
    mode: Literal["thinking", "nothinking"] | None,
    registry: ModelRegistry,
    store: AbstractSessionStore,
) -> AsyncIterator[str]:
    model_name = session.model
    reasoning = _MODE_TO_REASONING.get(mode) if mode else None
    llm = await registry.get_llm(model_name)
    human_msg = HumanMessage(content=message)
    context = session.truncated_messages(settings.max_messages_per_session) + [human_msg]

    try:
        await registry.acquire()
    except QueueOverloadError:
        yield _sse({"error": "overloaded", "detail": "Server at capacity. Try again shortly."})
        return

    chunks: list[str] = []
    try:
        async for chunk in llm.astream(context, reasoning=reasoning):
            token = chunk.content
            if token:
                chunks.append(str(token))
                yield _sse({"token": str(token)})
    except OllamaResponseError as exc:
        if exc.status_code == 400:
            yield _sse({"error": "bad_request", "detail": exc.error})
        else:
            yield _sse({"error": "ollama_error", "detail": exc.error})
        return
    except httpx.ConnectError:
        yield _sse({"error": "ollama_unavailable", "detail": "Ollama is not reachable."})
        return
    except Exception as exc:
        logger.exception("Unexpected error during streaming for chat_id=%s", session.chat_id)
        yield _sse({"error": "internal_error", "detail": str(exc)})
        return
    finally:
        registry.release()

    ai_msg = AIMessage(content="".join(chunks))
    await store.append_messages(session.chat_id, [human_msg, ai_msg])

    logger.info("stream complete chat_id=%s model=%s tokens=%d", session.chat_id, model_name, len(chunks))
    yield _sse({"done": True, "chat_id": session.chat_id, "model": model_name})


@router.post("/chat/stream")
async def post_stream_chat(
    request: ChatRequest,
    user: TokenUser = Depends(current_user),
    store: AbstractSessionStore = Depends(get_session_store),
    registry: ModelRegistry = Depends(get_model_registry),
) -> StreamingResponse:
    if request.chat_id:
        session = await store.get(request.chat_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"Chat session '{request.chat_id}' not found")
        model_name = request.model or session.model
    else:
        model_name = request.model or settings.default_model
        session = await store.create(str(uuid4()), model_name, user_id=UUID(user.id))

    if model_name not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' is not in the allowed list")

    return _streaming_response(_run_stream(session, request.message, request.mode, registry, store))


@router.get("/chat/{chat_id}/stream")
async def get_stream_chat(
    chat_id: str,
    message: str,
    mode: Literal["thinking", "nothinking"] | None = None,
    _: TokenUser = Depends(current_user),
    store: AbstractSessionStore = Depends(get_session_store),
    registry: ModelRegistry = Depends(get_model_registry),
) -> StreamingResponse:
    session = await store.get(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{chat_id}' not found")

    if session.model not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{session.model}' is not in the allowed list")

    return _streaming_response(_run_stream(session, message, mode, registry, store))
