"""
tools/twitter.py — Twitter / X API v2 style actions (optional OAuth1 credentials).
"""
from __future__ import annotations

from typing import Any

import httpx

from config import settings


def _has_twitter_creds() -> bool:
    return all(
        [
            settings.twitter_api_key,
            settings.twitter_api_secret,
            settings.twitter_access_token,
            settings.twitter_access_secret,
        ]
    )


async def _post_tweet(p: dict[str, Any]) -> dict[str, Any]:
    content = str(p.get("content", "")).strip()
    if not content:
        raise ValueError("content is required")
    if not _has_twitter_creds():
        return {"status": "simulated", "tweet_id": "dry-run", "chars": len(content)}
    # Real API would use OAuth1 — omitted for portability; return simulated in dev
    return {"status": "simulated", "tweet_id": "dev-placeholder", "chars": len(content)}


async def _reply(p: dict[str, Any]) -> dict[str, Any]:
    return {"status": "simulated", "in_reply_to": p.get("tweet_id")}


async def _search(p: dict[str, Any]) -> dict[str, Any]:
    q = str(p.get("query", "")).strip()
    lim = min(int(p.get("limit", 20) or 20), 50)
    if _has_twitter_creds():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    "https://api.twitter.com/2/tweets/search/recent",
                    params={"query": q, "max_results": lim},
                    headers={"Authorization": f"Bearer {settings.twitter_access_token}"},
                )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {"data": [{"id": "1", "text": f"Sample re: {q}"}][:lim]}


async def _get_trending(p: dict[str, Any]) -> dict[str, Any]:
    loc = str(p.get("location", "India"))
    return {"trends": [{"name": f"#{loc}Business", "volume": 1000}]}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "post_tweet": _post_tweet,
        "reply": _reply,
        "search": _search,
        "get_trending": _get_trending,
    }
    fn = dispatch.get(act)
    if not fn:
        raise ValueError(f"Unknown twitter action '{action}'")
    return await fn(params)
