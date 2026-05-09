import json
import logging
from typing import AsyncIterator, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings
from app.exceptions import QueueOverloadError
from app.model_registry import ModelRegistry
from app.session_store import SessionStore
from app.routers.chat import get_model_registry, get_session_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])

_MODE_TO_REASONING: dict[str, bool] = {
    "thinking": True,
    "nothinking": False,
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@router.get("/chat/{chat_id}/stream")
async def stream_chat(
    chat_id: str,
    message: str,
    mode: Literal["thinking", "nothinking"] | None = None,
    store: SessionStore = Depends(get_session_store),
    registry: ModelRegistry = Depends(get_model_registry),
) -> StreamingResponse:
    session = await store.get(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{chat_id}' not found")

    model_name = session.model
    if model_name not in settings.allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{model_name}' is not in the allowed list")

    reasoning = _MODE_TO_REASONING.get(mode) if mode else None
    llm = await registry.get_llm(model_name)
    human_msg = HumanMessage(content=message)
    context = session.truncated_messages(settings.max_messages_per_session) + [human_msg]

    async def event_generator() -> AsyncIterator[str]:
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
        except httpx.ConnectError:
            yield _sse({"error": "ollama_unavailable", "detail": "Ollama is not reachable."})
            return
        except Exception as exc:
            logger.exception("Unexpected error during streaming for chat_id=%s", chat_id)
            yield _sse({"error": "internal_error", "detail": str(exc)})
            return
        finally:
            registry.release()

        ai_msg = AIMessage(content="".join(chunks))
        await store.append_messages(chat_id, [human_msg, ai_msg])

        logger.info("stream complete chat_id=%s model=%s tokens=%d", chat_id, model_name, len(chunks))
        yield _sse({"done": True, "chat_id": chat_id, "model": model_name})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables Nginx buffering if behind a proxy
        },
    )
