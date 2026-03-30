"""
security/rate_limit.py
───────────────────────
Sliding-window rate limiting: Redis (optional) or in-memory fallback.
Plan-based limits for global and /execute endpoints.
"""
from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from config import settings

# Imported inside functions where needed to avoid circular import at module load.

ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
WINDOW_SECONDS = 60

PLAN_RATE_LIMITS = {
    "free": {"global_rpm": 20, "execute_rpm": 3},
    "starter": {"global_rpm": 60, "execute_rpm": 10},
    "pro": {"global_rpm": 200, "execute_rpm": 30},
    "pro_monthly": {"global_rpm": 200, "execute_rpm": 30},
    "enterprise": {"global_rpm": 1000, "execute_rpm": 100},
}

_windows: dict[str, deque] = defaultdict(deque)


def _redis_enabled() -> bool:
    return bool(settings.redis_enabled and (settings.redis_url or "").strip())


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def plan_limits_for_auth(auth: dict) -> dict[str, int]:
    plan = (auth or {}).get("plan") or "free"
    return PLAN_RATE_LIMITS.get(plan, PLAN_RATE_LIMITS["free"])


def _check_memory(key: str, limit: int) -> None:
    now = time.monotonic()
    window = _windows[key]
    while window and window[0] < now - WINDOW_SECONDS:
        window.popleft()
    if len(window) >= limit:
        retry_after = int(WINDOW_SECONDS - (now - window[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: max {limit} requests per {WINDOW_SECONDS}s. "
                f"Retry after {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)


async def _check_redis(key: str, limit: int) -> None:
    from memory.redis_client import get_redis

    r = await get_redis()
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - 60)
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, 60)
    results = await pipe.execute()
    count = int(results[2])
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit: {limit}/min",
        )


async def _apply_check(request: Request, endpoint_type: str, limit: int) -> None:
    if not ENABLED:
        return
    ip = _client_ip(request)
    key_full = f"rate:{ip}:{endpoint_type}"
    if _redis_enabled():
        await _check_redis(key_full, limit)
    else:
        _check_memory(f"{endpoint_type}:{ip}", limit)


def current_usage() -> dict:
    """Legacy: in-memory keys only (for dashboard when Redis off)."""
    now = time.monotonic()
    result = {}
    for key, window in _windows.items():
        active = sum(1 for t in window if t >= now - WINDOW_SECONDS)
        if active > 0:
            result[key] = active
    return result


async def current_usage_for_request(request: Request) -> dict[str, int]:
    """Current window counts for global + execute for this client IP."""
    ip = _client_ip(request)
    out = {"global": 0, "execute": 0}
    if _redis_enabled():
        try:
            from memory.redis_client import get_redis

            r = await get_redis()
            now = time.time()
            for kind in ("global", "execute"):
                k = f"rate:{ip}:{kind}"
                await r.zremrangebyscore(k, 0, now - 60)
                out[kind] = int(await r.zcard(k))
        except Exception:
            out = {"global": 0, "execute": 0}
    else:
        now = time.monotonic()
        for kind in ("global", "execute"):
            w = _windows.get(f"{kind}:{ip}")
            if w:
                out[kind] = sum(1 for t in w if t >= now - WINDOW_SECONDS)
    return out


def _require_auth_dep():
    from security.auth import require_auth

    return require_auth


async def rate_limit(
    request: Request,
    auth: dict = Depends(_require_auth_dep()),
) -> None:
    lim = plan_limits_for_auth(auth)["global_rpm"]
    await _apply_check(request, "global", lim)


async def execute_rate_limit(
    request: Request,
    auth: dict = Depends(_require_auth_dep()),
) -> None:
    lim = plan_limits_for_auth(auth)["execute_rpm"]
    await _apply_check(request, "execute", lim)


async def auth_rate_limit(request: Request) -> None:
    if not ENABLED:
        return
    ip = _client_ip(request)
    if _redis_enabled():
        await _check_redis(f"rate:{ip}:auth", 20)
    else:
        _check_memory(f"auth:{ip}", 20)


# Backward compat for tests (in-memory sliding window only)
_check = _check_memory
