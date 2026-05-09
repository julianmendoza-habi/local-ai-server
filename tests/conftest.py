import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    # app.router.lifespan_context triggers the @asynccontextmanager lifespan,
    # which initialises SessionStore and ModelRegistry before any request.
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
