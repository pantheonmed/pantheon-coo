"""
tools/researcher.py — Google News RSS, research synthesis, keyword schedules.
"""
from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import aiosqlite
import httpx

from agents.model_router import call_model
from config import settings

_INDUSTRY_QUERIES: dict[str, str] = {
    "medical": "medical devices healthcare India",
    "tech": "technology startups India",
    "finance": "finance banking India",
    "pharma": "pharmaceutical India",
    "real_estate": "real estate India property",
}


def _rss_url(query: str, language: str = "en") -> str:
    q = quote_plus(query)
    hl = "en-IN" if language.startswith("en") else language
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl=IN"


def _simple_sentiment(title: str) -> str:
    t = (title or "").lower()
    neg = ("crash", "fall", "loss", "fraud", "ban", "recall", "death")
    pos = ("growth", "launch", "record", "profit", "deal", "award")
    if any(w in t for w in neg):
        return "negative"
    if any(w in t for w in pos):
        return "positive"
    return "neutral"


def _parse_rss(xml_text: str, limit: int) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[dict[str, Any]] = []
    for it in channel.findall("item"):
        if len(items) >= limit:
            break
        title_el = it.find("title")
        link_el = it.find("link")
        pub_el = it.find("pubDate")
        desc_el = it.find("description")
        source_el = it.find("source")
        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
        url = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
        date = (pub_el.text or "").strip() if pub_el is not None and pub_el.text else ""
        summary = ""
        if desc_el is not None and desc_el.text:
            summary = re.sub(r"<[^>]+>", "", desc_el.text).strip()[:500]
        src = (source_el.text or "Google News").strip() if source_el is not None else "Google News"
        items.append(
            {
                "title": title,
                "summary": summary,
                "url": url,
                "source": src,
                "date": date,
                "sentiment": _simple_sentiment(title),
            }
        )
    return items


async def _search_news(p: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(p.get("query") or "").strip()
    if not query:
        raise ValueError("query is required.")
    limit = min(int(p.get("limit") or 10), 50)
    language = str(p.get("language") or "en")
    url = _rss_url(query, language)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
    return _parse_rss(r.text, limit)


async def _research_topic(p: dict[str, Any]) -> dict[str, Any]:
    topic = str(p.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic is required.")
    depth = str(p.get("depth") or "standard").lower()
    save = bool(p.get("save_to_file", True))
    bullets = await _search_news({"query": topic, "limit": 8 if depth == "quick" else 12})
    lines = "\n".join(f"- {b.get('title')}: {b.get('url')}" for b in bullets[:10])
    resp = call_model(
        system="You are a research synthesizer for executives. Be concise and factual.",
        user=f"Topic: {topic}\nDepth: {depth}\nSources (titles + URLs):\n{lines}\n\n"
        "Provide: (1) 3–6 sentence summary (2) 5–10 key facts as bullets (3) list of source titles used.\n"
        "Format as markdown with headings ## Summary, ## Key facts, ## Sources.",
        use_fast=depth == "quick",
    )
    summary = resp.text[:2000]
    key_facts = [ln.strip("- •\t ") for ln in resp.text.splitlines() if ln.strip().startswith(("-", "•", "*"))]
    sources_used = [b.get("url", "") for b in bullets if b.get("url")]
    file_path = ""
    if save:
        out_dir = Path(settings.workspace_dir).resolve() / "research"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-z0-9_]+", "_", topic.lower())[:50]
        fp = out_dir / f"research_{safe}.md"
        fp.write_text(f"# Research: {topic}\n\n{resp.text}", encoding="utf-8")
        file_path = str(fp)
    return {
        "summary": summary,
        "key_facts": key_facts[:15] if key_facts else [summary[:200]],
        "sources_used": sources_used,
        "file_path": file_path,
    }


async def _monitor_keyword(p: dict[str, Any]) -> dict[str, Any]:
    keywords = p.get("keywords") or []
    if not keywords:
        raise ValueError("keywords list is required.")
    kw_list = [str(x).strip() for x in keywords if str(x).strip()]
    hours = max(1, min(int(p.get("check_interval_hours") or 24), 168))
    cron = f"0 */{hours} * * *"
    from scheduler import _next_run

    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    next_run = _next_run(cron).isoformat()
    name = f"News monitor: {', '.join(kw_list[:3])}"
    command = (
        f"Search news for keywords {kw_list} and save a short digest to workspace "
        f"(researcher tool / industry brief)."
    )
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            """INSERT INTO schedules (schedule_id, name, command, cron, enabled, next_run_at, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, name[:200], command[:2000], cron, 1, next_run, now),
        )
        await db.commit()
    return {"schedule_id": sid, "keywords": kw_list, "next_check": next_run}


async def _get_industry_news(p: dict[str, Any]) -> list[dict[str, Any]]:
    industry = str(p.get("industry") or "").strip().lower().replace("-", "_")
    if industry not in _INDUSTRY_QUERIES:
        raise ValueError(f"industry must be one of: {list(_INDUSTRY_QUERIES)}")
    limit = min(int(p.get("limit") or 5), 20)
    q = _INDUSTRY_QUERIES[industry]
    return await _search_news({"query": q, "limit": limit, "language": "en"})


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    if act == "search_news":
        return await _search_news(params)
    if act == "research_topic":
        return await _research_topic(params)
    if act == "monitor_keyword":
        return await _monitor_keyword(params)
    if act == "get_industry_news":
        return await _get_industry_news(params)
    raise ValueError(
        f"Unknown researcher action: '{action}'. "
        "Available: search_news, research_topic, monitor_keyword, get_industry_news"
    )
