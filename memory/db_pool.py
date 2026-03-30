"""
memory/db_pool.py — async SQLite (aiosqlite) with optional PostgreSQL (asyncpg).

When ``DATABASE_URL`` contains ``postgresql`` the pool reports ``backend == "postgresql"``.
Connections from ``acquire()`` use PostgreSQL only if ``POSTGRES_STORE_ENABLED=true``;
otherwise SQLite via ``db_path`` is used so the existing store layer keeps working until migrated.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import aiosqlite

from config import settings

_log = logging.getLogger("pantheon.db")

_pool: "DBPool | None" = None


def normalize_asyncpg_dsn(url: str) -> str:
    """Strip SQLAlchemy-style ``+asyncpg`` for direct asyncpg.connect."""
    u = (url or "").strip()
    return u.replace("postgresql+asyncpg://", "postgresql://", 1)


class DBPool:
    def __init__(self, db_path: str, pool_size: int = 10):
        self._db_path = db_path
        self._pool_size = pool_size
        self._semaphore = asyncio.Semaphore(pool_size)
        self._backend = "sqlite"
        self._pg_dsn: str | None = None
        du = (settings.database_url or "").strip()
        if du:
            dul = du.lower()
            if "postgresql" in dul:
                self._backend = "postgresql"
                self._pg_dsn = normalize_asyncpg_dsn(du)
            elif "mysql" in dul:
                self._backend = "mysql"

    @property
    def backend(self) -> str:
        """Resolved backend from ``DATABASE_URL`` (``sqlite`` if unset)."""
        return self._backend

    def _use_postgres_acquire(self) -> bool:
        return self._backend == "postgresql" and bool(getattr(settings, "postgres_store_enabled", False))

    async def _get_pg_connection(self):
        import asyncpg

        assert self._pg_dsn is not None
        return await asyncpg.connect(self._pg_dsn)

    @asynccontextmanager
    async def acquire(self):
        async with self._semaphore:
            t0 = time.monotonic()
            if self._use_postgres_acquire():
                conn = await self._get_pg_connection()
                try:
                    yield conn
                finally:
                    await conn.close()
            else:
                async with aiosqlite.connect(self._db_path) as db:
                    db.row_factory = aiosqlite.Row
                    try:
                        yield db
                    finally:
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        if elapsed_ms > 500:
                            _log.error("SLOW QUERY: %.0fms (connection scope)", elapsed_ms)
                        elif elapsed_ms > 100:
                            _log.warning("Slow query: %.0fms", elapsed_ms)


def init_pool(db_path: str, pool_size: int = 10) -> None:
    global _pool
    _pool = DBPool(db_path, pool_size)


def get_pool() -> DBPool:
    global _pool
    if _pool is None:
        init_pool(settings.db_path, pool_size=10)
    return _pool  # type: ignore[return-value]
