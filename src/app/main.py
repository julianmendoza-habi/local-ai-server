import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db as db_module
from app.config import settings
from app.exceptions import QueueOverloadError, queue_overload_handler
from app.model_registry import ModelRegistry
from app.session_store import PostgresSessionStore, SessionStore
from app.routers import chat as chat_module
from app.routers.chat import router as chat_router
from app.routers.streaming import router as streaming_router
from app.routers.admin import router as admin_router
from app.auth.router import router as auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting up local-ai-server")

    pool: asyncpg.Pool | None = None
    if settings.database_url:
        pool = await asyncpg.create_pool(settings.database_url)
        db_module._pool = pool
        store: PostgresSessionStore | SessionStore = PostgresSessionStore(pool)
        logger.info("Using PostgreSQL session store")
    else:
        store = SessionStore()
        logger.info("Using in-memory session store (no DATABASE_URL set)")

    registry = ModelRegistry()
    chat_module._session_store = store
    chat_module._model_registry = registry

    yield

    if pool:
        await pool.close()
    logger.info("Shutting down local-ai-server")


app = FastAPI(
    title="Local AI Server",
    description="Stateful AI gateway over a local Ollama instance",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(QueueOverloadError, queue_overload_handler)  # type: ignore[arg-type]


@app.exception_handler(Exception)
async def internal_server_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal server error"},
    )


@app.exception_handler(httpx.ConnectError)
async def ollama_connect_handler(request: Request, exc: httpx.ConnectError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "Ollama is not reachable. Is it running on the configured URL?"},
    )


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(streaming_router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}
