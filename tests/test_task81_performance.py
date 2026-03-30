"""Task 81 — caching, indexes, queue depth, lazy tool imports."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import memory.store as store
from config import settings


@pytest.mark.asyncio
async def test_cached_decorator_passthrough_when_redis_disabled(monkeypatch):
    monkeypatch.setattr(settings, "redis_enabled", False)
    from memory.redis_client import cached

    calls = 0

    @cached(ttl=60)
    async def expensive(x: int) -> dict:
        nonlocal calls
        calls += 1
        return {"v": x}

    assert await expensive(1) == {"v": 1}
    assert await expensive(1) == {"v": 1}
    assert calls == 2


def test_migration_0017_perf_indexes_sql_exists():
    root = Path(__file__).resolve().parents[1]
    p = root / "migrations" / "versions" / "0017_perf_indexes.sql"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "idx_tasks_user_created" in text
    assert "idx_tasks_status_created" in text


def test_startup_client_under_five_seconds():
    from main import app
    from fastapi.testclient import TestClient

    t0 = time.monotonic()
    with TestClient(app, raise_server_exceptions=True):
        pass
    assert (time.monotonic() - t0) < 5.0


@pytest.mark.asyncio
async def test_get_queue_depth_returns_int():
    await store.init()
    d = await store.get_queue_depth()
    assert isinstance(d, int)
    assert d >= 0


@pytest.mark.asyncio
async def test_lazy_loader_imports_tool_module():
    from tools.lazy_loader import get_tool

    mod = await get_tool("filesystem")
    assert hasattr(mod, "__name__")
    assert "filesystem" in mod.__name__
