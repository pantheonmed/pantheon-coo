"""Task 51 — Redis client, optional Redis rate limit, requirements & compose."""
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_cache_get_missing_returns_none_mock_redis():
    from memory import redis_client as rc

    mock_r = MagicMock()
    mock_r.get = AsyncMock(return_value=None)

    async def fake_get_redis():
        return mock_r

    with patch.object(rc, "get_redis", fake_get_redis):
        with patch.object(rc.settings, "redis_enabled", True):
            with patch.object(rc.settings, "redis_url", "redis://localhost:6379/0"):
                out = await rc.cache_get("k")
    assert out is None


@pytest.mark.asyncio
async def test_cache_set_calls_setex_with_ttl():
    from memory import redis_client as rc

    mock_r = MagicMock()
    mock_r.setex = AsyncMock()

    async def fake_get_redis():
        return mock_r

    with patch.object(rc, "get_redis", fake_get_redis):
        with patch.object(rc.settings, "redis_enabled", True):
            with patch.object(rc.settings, "redis_url", "redis://x"):
                with patch.object(rc.settings, "cache_ttl_seconds", 300):
                    await rc.cache_set("mykey", "v", ttl=120)
    mock_r.setex.assert_awaited_once()
    args, _ = mock_r.setex.await_args
    assert args[0] == "cache:mykey"
    assert args[1] == 120
    assert args[2] == "v"


def test_rate_limit_in_memory_still_works_backward_compat():
    """Use sync _check_memory only — asyncio.run() breaks pytest-asyncio session loop."""
    import importlib

    rl = importlib.import_module("security.rate_limit")
    rl._windows.clear()
    with patch.object(rl, "ENABLED", True):
        for _ in range(5):
            rl._check_memory("compat_key", 5)
        with pytest.raises(HTTPException) as ei:
            rl._check_memory("compat_key", 5)
        assert ei.value.status_code == 429


def test_requirements_contains_redis_packages():
    root = Path(__file__).resolve().parents[1]
    txt = (root / "requirements.txt").read_text()
    assert "redis==5.0.4" in txt
    assert "hiredis==2.3.2" in txt


def test_docker_compose_has_redis_service():
    root = Path(__file__).resolve().parents[1]
    yml = (root / "docker-compose.yml").read_text()
    assert "redis:" in yml
    assert "6380:6379" in yml
    assert "pantheon_coo_redis" in yml
    assert 'profiles: ["redis"]' in yml or "profiles: [\"redis\"]" in yml


@pytest.mark.asyncio
async def test_cache_get_none_when_redis_disabled():
    from memory import redis_client as rc

    with patch.object(rc.settings, "redis_enabled", False):
        assert await rc.cache_get("any") is None


@pytest.mark.asyncio
async def test_close_redis_clears_singleton():
    from memory import redis_client as rc

    rc._redis = object()
    await rc.close_redis()
    assert rc._redis is None
