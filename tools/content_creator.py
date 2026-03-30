"""
tools/content_creator.py — Blog, social, email, ads, content calendar (Claude → markdown files).
"""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any

from config import settings
from agents.model_router import call_model

def _ws_root() -> Path:
    return Path(settings.workspace_dir).resolve()


def _content_path(prefix: str) -> Path:
    d = _ws_root() / "content"
    d.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    safe = re.sub(r"[^a-z0-9_]+", "_", prefix.lower())[:40]
    return d / f"{safe}_{ts}.md"


async def _gen_md(system: str, user: str) -> str:
    def _sync() -> str:
        r = call_model(system, user, use_fast=True, max_tokens=4096)
        return (r.text or "").strip()

    return await asyncio.to_thread(_sync)


_SYS = """You are a professional marketing copywriter. Output markdown only, no preamble."""


async def _write_blog_post(p: dict[str, Any]) -> dict[str, Any]:
    topic = str(p.get("topic") or "")
    kws = p.get("keywords") or []
    wc = int(p.get("word_count") or 1000)
    tone = str(p.get("tone") or "professional")
    user = f"Write a ~{wc}-word blog post.\nTopic: {topic}\nKeywords: {kws}\nTone: {tone}"
    body = await _gen_md(_SYS, user)
    path = _content_path("blog_post")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}


async def _write_social_post(p: dict[str, Any]) -> dict[str, Any]:
    platform = str(p.get("platform") or "linkedin")
    topic = str(p.get("topic") or "")
    goal = str(p.get("goal") or "engagement")
    tags = bool(p.get("include_hashtags", True))
    user = f"Platform: {platform}\nTopic: {topic}\nGoal: {goal}\nInclude hashtags: {tags}"
    body = await _gen_md(_SYS, user)
    path = _content_path(f"social_{platform}")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}


async def _write_email_campaign(p: dict[str, Any]) -> dict[str, Any]:
    user = f"""Email campaign:
type: {p.get("campaign_type", "newsletter")}
product: {p.get("product_name", "")}
message: {p.get("key_message", "")}
CTA text: {p.get("cta_text", "Learn more")}
"""
    body = await _gen_md(_SYS, user)
    path = _content_path("email_campaign")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}


async def _create_ad_copy(p: dict[str, Any]) -> dict[str, Any]:
    user = f"""Ad copy for {p.get("platform", "google")}.
Product: {p.get("product", "")}
Audience: {p.get("target_audience", "")}
"""
    body = await _gen_md(_SYS, user)
    path = _content_path("ad_copy")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "bytes": path.stat().st_size}


async def _repurpose_content(p: dict[str, Any]) -> dict[str, Any]:
    src = str(p.get("source_text") or "")
    fmts = p.get("output_formats") or ["tweet", "linkedin"]
    user = f"Repurpose this text into formats {fmts}:\n\n{src[:8000]}"
    body = await _gen_md(_SYS, user)
    path = _content_path("repurpose")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "formats": fmts}


async def _create_content_calendar(p: dict[str, Any]) -> dict[str, Any]:
    brand = str(p.get("brand_name") or "")
    industry = str(p.get("industry") or "")
    platforms = p.get("platforms") or ["linkedin"]
    ppw = int(p.get("posts_per_week") or 5)
    month = str(p.get("month") or "")
    user = f"""30-day content calendar as markdown table.
Brand: {brand}
Industry: {industry}
Platforms: {platforms}
Posts per week target: {ppw}
Month label: {month}
Columns: Date | Platform | Topic | Content Type | Status
Generate ~30 rows."""
    body = await _gen_md(_SYS, user)
    path = _content_path("calendar")
    path.write_text(body, encoding="utf-8")
    return {"path": str(path), "rows_hint": 30}


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()
    if a == "write_blog_post":
        return await _write_blog_post(params)
    if a == "write_social_post":
        return await _write_social_post(params)
    if a == "write_email_campaign":
        return await _write_email_campaign(params)
    if a == "create_ad_copy":
        return await _create_ad_copy(params)
    if a == "repurpose_content":
        return await _repurpose_content(params)
    if a == "create_content_calendar":
        return await _create_content_calendar(params)
    raise ValueError(f"Unknown content_creator action: {action}")
