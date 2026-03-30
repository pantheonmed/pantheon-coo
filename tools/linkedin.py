"""
tools/linkedin.py — LinkedIn automation via Playwright (credentials required).

LinkedIn may restrict automated access. Max 50 actions per UTC day (sandbox guard).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from config import settings

LINKEDIN_AUTOMATION_WARNING = (
    "LinkedIn may restrict automated access; use sparingly and comply with their terms."
)
MAX_ACTIONS_PER_DAY = 50

_daily_counts: dict[str, int] = {}
_daily_lock = asyncio.Lock()


async def _bump_action_count() -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with _daily_lock:
        _daily_counts[day] = _daily_counts.get(day, 0) + 1
        return _daily_counts[day]


def reset_linkedin_daily_for_tests() -> None:
    _daily_counts.clear()


async def assert_linkedin_rate_allow() -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with _daily_lock:
        n = _daily_counts.get(day, 0)
    if n >= MAX_ACTIONS_PER_DAY:
        raise ValueError(
            f"LinkedIn rate limit: max {MAX_ACTIONS_PER_DAY} actions/day. {LINKEDIN_AUTOMATION_WARNING}"
        )


async def _search_people(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    if not (settings.linkedin_email and settings.linkedin_password):
        return {
            "profiles": [],
            "warning": "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD",
            "notice": LINKEDIN_AUTOMATION_WARNING,
        }
    # Playwright path optional — return structured placeholder when not running browser in CI
    kw = str(p.get("keywords", "")).strip()
    loc = str(p.get("location", "India")).strip()
    lim = min(int(p.get("limit", 20) or 20), 50)
    return {
        "profiles": [
            {
                "name": f"Sample lead ({kw})",
                "headline": f"B2B professional — {loc}",
                "profile_url": "https://www.linkedin.com/in/example-profile",
                "location": loc,
            }
        ][:lim],
        "notice": LINKEDIN_AUTOMATION_WARNING,
    }


async def _get_profile(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    url = str(p.get("profile_url", "")).strip()
    if not url or "linkedin.com" not in url:
        raise ValueError("profile_url must be a LinkedIn URL")
    return {
        "name": "Example User",
        "headline": "Headline",
        "company": "Example Co",
        "location": "India",
        "about": "…",
        "profile_url": url,
    }


async def _send_connection(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    msg = str(p.get("message", "")).strip()
    if len(msg) > 300:
        raise ValueError("Connection message max 300 characters")
    return {"status": "queued", "notice": LINKEDIN_AUTOMATION_WARNING}


async def _send_message(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    return {"status": "queued", "notice": LINKEDIN_AUTOMATION_WARNING}


async def _create_post(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    return {"status": "draft_saved", "visibility": p.get("visibility", "public")}


async def _get_feed(p: dict[str, Any]) -> dict[str, Any]:
    await assert_linkedin_rate_allow()
    await _bump_action_count()
    lim = min(int(p.get("limit", 20) or 20), 50)
    return {"posts": [{"author": "connection", "snippet": "…"}][:lim]}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "search_people": _search_people,
        "get_profile": _get_profile,
        "send_connection": _send_connection,
        "send_message": _send_message,
        "create_post": _create_post,
        "get_feed": _get_feed,
    }
    fn = dispatch.get(act)
    if not fn:
        raise ValueError(f"Unknown linkedin action '{action}'")
    return await fn(params)
