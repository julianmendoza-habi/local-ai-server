import asyncio
import logging

from langchain_ollama import ChatOllama

from app.config import settings
from app.exceptions import QueueOverloadError

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Cache of ChatOllama instances with semaphore-based concurrency control.

    A single semaphore gates all Ollama calls regardless of model, matching
    the physical constraint that a home server can only run N inferences at once.
    The _waiting counter lets us reject requests before they stack up in the
    semaphore's internal waiter list, so we can return 503 immediately instead
    of silently queuing unlimited requests.
    """

    def __init__(self) -> None:
        self._models: dict[str, ChatOllama] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_ollama_requests)
        self._waiting: int = 0

    async def get_llm(self, model_name: str) -> ChatOllama:
        """Return a cached ChatOllama instance, creating it lazily if needed."""
        if model_name not in self._models:
            async with self._lock:
                # Double-checked: another coroutine may have created it while we waited
                if model_name not in self._models:
                    logger.info("Initialising model client for '%s'", model_name)
                    self._models[model_name] = ChatOllama(
                        model=model_name,
                        base_url=settings.ollama_base_url,
                        keep_alive=f"{settings.ollama_keep_alive}s",
                    )
        return self._models[model_name]

    async def acquire(self) -> None:
        """Block until an inference slot is free, or raise QueueOverloadError."""
        if self._waiting >= settings.max_queue_size:
            raise QueueOverloadError()
        self._waiting += 1
        try:
            await self._semaphore.acquire()
        finally:
            # Decrement whether we got the semaphore or were interrupted
            self._waiting -= 1

    def release(self) -> None:
        self._semaphore.release()
