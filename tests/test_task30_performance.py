"""
Task 30 — DB pool, health metrics, load_test script.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from memory.db_pool import DBPool


@pytest.mark.asyncio
async def test_db_pool_acquire_and_release():
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "pooltest.db"
    pool = DBPool(str(path), pool_size=4)
    async with pool.acquire() as db:
        async with db.execute("SELECT 1") as cur:
            row = await cur.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_db_pool_semaphore_limits_concurrent_acquires():
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "pooltest2.db"
    pool = DBPool(str(path), pool_size=3)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def work():
        nonlocal active, max_active
        async with pool.acquire() as db:
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.04)
            async with lock:
                active -= 1

    await asyncio.gather(*[work() for _ in range(10)])
    assert max_active <= 3


def test_health_returns_memory_uptime_pool_fields(client: TestClient):
    d = client.get("/health").json()
    assert "memory_mb" in d
    assert "uptime_seconds" in d
    assert d.get("db_pool_size") == 10


def test_load_test_script_exists_and_has_argparse():
    script = Path(__file__).resolve().parent.parent / "scripts" / "load_test.py"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "argparse" in text
    assert "--url" in text
    assert "--users" in text


def test_store_uses_get_pool_not_raw_aiosqlite_connect():
    store_path = Path(__file__).resolve().parent.parent / "memory" / "store.py"
    text = store_path.read_text(encoding="utf-8")
    assert "get_pool().acquire()" in text
    assert "aiosqlite.connect" not in text
