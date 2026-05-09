import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import QueueOverloadError
from app.model_registry import ModelRegistry


@pytest.fixture
def registry():
    return ModelRegistry()


@pytest.mark.asyncio
async def test_get_llm_caches_instance(registry):
    with patch("app.model_registry.ChatOllama") as MockOllama:
        MockOllama.return_value = MagicMock()
        llm1 = await registry.get_llm("gemma4:e2b")
        llm2 = await registry.get_llm("gemma4:e2b")
        assert llm1 is llm2
        MockOllama.assert_called_once()


@pytest.mark.asyncio
async def test_get_llm_different_models_separate_instances(registry):
    with patch("app.model_registry.ChatOllama") as MockOllama:
        MockOllama.side_effect = lambda **kwargs: MagicMock(model=kwargs["model"])
        llm_a = await registry.get_llm("gemma4:e2b")
        llm_b = await registry.get_llm("llama3")
        assert llm_a is not llm_b
        assert MockOllama.call_count == 2


@pytest.mark.asyncio
async def test_acquire_release_basic(registry):
    await registry.acquire()
    assert registry._semaphore._value == 1  # 2 - 1 = 1 remaining
    registry.release()
    assert registry._semaphore._value == 2


@pytest.mark.asyncio
async def test_queue_overload_raises(registry):
    # Fill both semaphore slots and the queue
    from app.config import settings

    # Exhaust the semaphore permits without releasing
    acquired = []
    for _ in range(settings.max_concurrent_ollama_requests):
        await registry._semaphore.acquire()
        acquired.append(True)

    # Now simulate max_queue_size waiters already registered
    registry._waiting = settings.max_queue_size

    with pytest.raises(QueueOverloadError):
        await registry.acquire()

    # Cleanup
    for _ in acquired:
        registry._semaphore.release()


@pytest.mark.asyncio
async def test_concurrent_acquire_blocks_at_limit(registry):
    """Only max_concurrent requests should be active simultaneously."""
    from app.config import settings

    active = 0
    max_active = 0
    results = []

    async def task():
        nonlocal active, max_active
        await registry.acquire()
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)  # simulate work
        active -= 1
        registry.release()
        results.append(True)

    await asyncio.gather(*[task() for _ in range(settings.max_concurrent_ollama_requests + 2)])

    assert max_active <= settings.max_concurrent_ollama_requests
    assert len(results) == settings.max_concurrent_ollama_requests + 2
