import asyncpg

_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "DB pool not initialized"
    return _pool
