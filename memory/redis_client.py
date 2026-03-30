"""
memory/redis_client.py — async Redis connection, cache helpers, rate-limit support.
"""
from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Callable, Optional, TypeVar

from config import settings

F = TypeVar("F", bound=Callable[..., Any])

_redis: Optional[object] = None


async def get_redis():
    global _redis
    if not settings.redis_enabled or not (settings.redis_url or "").strip():
        raise RuntimeError("Redis is not enabled or redis_url is empty")
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None


async def cache_get(key: str) -> Optional[str]:
    if not settings.redis_enabled:
        return None
    r = await get_redis()
    return await r.get(f"cache:{key}")


async def cache_set(key: str, value: str, ttl: Optional[int] = None) -> None:
    if not settings.redis_enabled:
        return
    r = await get_redis()
    t = int(ttl if ttl is not None else settings.cache_ttl_seconds)
    await r.setex(f"cache:{key}", t, value)


async def cache_delete(key: str) -> None:
    if not settings.redis_enabled:
        return
    r = await get_redis()
    await r.delete(f"cache:{key}")


async def cache_delete_prefix(prefix: str) -> None:
    """Delete all cache:prefix* keys (SCAN)."""
    if not settings.redis_enabled:
        return
    r = await get_redis()
    p = f"cache:{prefix}"
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor=cursor, match=f"{p}*", count=100)
        if keys:
            await r.delete(*keys)
        if cursor == 0:
            break


def cached(ttl: int = 300, key_prefix: str = ""):
    """
    Redis JSON cache for async callables. When Redis is disabled, calls through directly.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not settings.redis_enabled:
                return await func(*args, **kwargs)
            raw = f"{key_prefix or func.__name__}:{repr(args)}:{repr(sorted(kwargs.items()))}"
            h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:48]
            cache_key = f"{key_prefix or func.__name__}:{h}"
            hit = await cache_get(cache_key)
            if hit:
                return json.loads(hit)
            result = await func(*args, **kwargs)
            try:
                await cache_set(cache_key, json.dumps(result, default=str), ttl)
            except Exception:
                pass
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
