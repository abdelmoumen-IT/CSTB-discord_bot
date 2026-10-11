import os
import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=1,
        max_size=5,
        command_timeout=30,
        max_inactive_connection_lifetime=240,
        statement_cache_size=0,
    )
    return _pool


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() first.")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None