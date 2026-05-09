import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.exceptions import QueueOverloadError, queue_overload_handler
from app.model_registry import ModelRegistry
from app.session_store import SessionStore
from app.routers import chat as chat_module
from app.routers.chat import router as chat_router
from app.routers.streaming import router as streaming_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up local-ai-server")
    store = SessionStore()
    registry = ModelRegistry()

    # Wire singletons into the chat router's dependency injectors
    chat_module._session_store = store
    chat_module._model_registry = registry

    yield

    logger.info("Shutting down local-ai-server")


app = FastAPI(
    title="Local AI Server",
    description="Stateful AI gateway over a local Ollama instance",
    version="0.1.0",
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(QueueOverloadError, queue_overload_handler)  # type: ignore[arg-type]


@app.exception_handler(httpx.ConnectError)
async def ollama_connect_handler(request: Request, exc: httpx.ConnectError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "Ollama is not reachable. Is it running on the configured URL?"},
    )


# Routers
app.include_router(chat_router)
app.include_router(streaming_router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}
