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
from security.sandbox import workspace_root
from tools.task_context import get_task_user_id

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


def _normalize_row(
    title: str,
    url: str,
    summary: str,
    source: str,
    date: str,
) -> dict[str, Any]:
    return {
        "title": title or "",
        "summary": (summary or "")[:600],
        "url": url or "",
        "source": source or "web",
        "date": date or "",
        "sentiment": _simple_sentiment(title or ""),
    }


async def _effective_search_keys() -> tuple[str, str]:
    tav = (getattr(settings, "tavily_api_key", None) or "").strip()
    news = (getattr(settings, "news_api_key", None) or "").strip()
    uid = get_task_user_id()
    if uid:
        try:
            import memory.store as store_mod

            u = await store_mod.get_user_settings(uid)
            if u:
                tav = (u.get("tavily_api_key") or tav or "").strip()
                news = (u.get("news_api_key") or news or "").strip()
        except Exception:
            pass
    return tav, news


async def duckduckgo_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Real web search via DuckDuckGo free endpoint.
    Returns: [{title, url, summary, source, date}, ...]
    """
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    results: list[dict[str, Any]] = []
    related = data.get("RelatedTopics", []) or []
    for item in related[:limit]:
        txt = item.get("Text") if isinstance(item, dict) else None
        if txt:
            results.append(
                {
                    "title": txt[:100],
                    "url": item.get("FirstURL", "") if isinstance(item, dict) else "",
                    "summary": txt,
                    "source": "DuckDuckGo",
                    "date": "",
                    "sentiment": _simple_sentiment(txt),
                }
            )
    return results


async def real_web_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Alias for :func:`duckduckgo_search` (backwards compatibility)."""
    return await duckduckgo_search(query, limit)


async def smart_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Try APIs in order: Tavily → NewsAPI → DuckDuckGo → Google News RSS.
    Usually returns results without any paid key (RSS / DDG).
    """
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(int(limit), 50))
    tavily_key, news_key = await _effective_search_keys()

    if tavily_key:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": q,
                        "max_results": lim,
                        "search_depth": "advanced",
                    },
                )
                data = r.json()
                rows = data.get("results") or []
                if rows:
                    out: list[dict[str, Any]] = []
                    for x in rows[:lim]:
                        if not isinstance(x, dict):
                            continue
                        content = x.get("content") or ""
                        out.append(
                            _normalize_row(
                                x.get("title", ""),
                                x.get("url", ""),
                                (content[:600] if isinstance(content, str) else ""),
                                x.get("source", "") or "",
                                x.get("published_date", "") or "",
                            )
                        )
                    if out:
                        return out
        except Exception:
            pass

    if news_key:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": q,
                        "apiKey": news_key,
                        "pageSize": lim,
                        "sortBy": "publishedAt",
                        "language": "en",
                    },
                )
                data = r.json()
                arts = data.get("articles") or []
                if arts:
                    out = []
                    for x in arts[:lim]:
                        if not isinstance(x, dict):
                            continue
                        src = x.get("source") or {}
                        name = src.get("name", "") if isinstance(src, dict) else ""
                        out.append(
                            _normalize_row(
                                x.get("title", "") or "",
                                x.get("url", "") or "",
                                x.get("description", "") or "",
                                name,
                                x.get("publishedAt", "") or "",
                            )
                        )
                    if out:
                        return out
        except Exception:
            pass

    try:
        dd = await duckduckgo_search(q, lim)
        if dd:
            return dd
    except Exception:
        pass

    try:
        rss_url = _rss_url(q, "en")
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(rss_url)
            r.raise_for_status()
        return _parse_rss(r.text, lim)
    except Exception:
        return []


def _normalize_search_hit(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize rows to the schema used by search_news / synthesis."""
    title = item.get("title", "")
    return {
        "title": title,
        "summary": (item.get("summary") or "")[:500],
        "url": item.get("url", ""),
        "source": item.get("source", "") or "web",
        "date": item.get("date", "") or item.get("published", ""),
        "sentiment": item.get("sentiment") or _simple_sentiment(title),
    }


async def _search_news(p: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(p.get("query") or "").strip()
    if not query:
        raise ValueError("query is required.")
    limit = min(int(p.get("limit") or 10), 50)
    language = str(p.get("language") or "en")

    items = await smart_search(query, limit)
    if items:
        return [_normalize_search_hit(it) for it in items]

    backend = str(getattr(settings, "news_search_backend", "google_rss") or "google_rss").lower()
    if backend == "duckduckgo":
        try:
            items = await duckduckgo_search(query, limit=limit)
            return [_normalize_search_hit(it) for it in items]
        except Exception:
            pass

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
    lim = 10 if depth == "quick" else 10
    raw = await smart_search(topic, lim)
    if not raw:
        raw = [
            {
                "title": "Model knowledge base",
                "summary": f"General knowledge context for {topic} (no live web hits).",
                "url": "",
                "source": "fallback",
                "date": "",
            }
        ]
    bullets = [_normalize_search_hit(it) for it in raw]
    sources_text = "\n".join(
        f"- {b.get('title', '')}: {(b.get('summary') or '')[:300]}"
        for b in bullets[:15]
    )
    report_prompt = f"""Create a comprehensive research report about: {topic}

Based on these sources (titles + excerpts):
{sources_text}

Report must include:
1. Executive Summary (3–4 sentences)
2. Market Overview
3. Key Players / Developments
4. Recent News & Trends
5. Opportunities & Risks
6. Recommendations
7. Sources List (reference titles; cite URLs where present)

Make it professional and detailed (500+ words). Use markdown formatting with clear ## headings."""
    resp = call_model(
        system="You are a senior research analyst. Use the sources; if a source lacks a URL, still reflect its theme. Be factual; note uncertainty where needed.",
        user=report_prompt,
        use_fast=depth == "quick",
        max_tokens=4096,
    )
    report = resp.text
    word_count = len(report.split())
    summary = report[:2000]
    key_facts = [
        ln.strip("- •\t ")
        for ln in report.splitlines()
        if ln.strip().startswith(("-", "•", "*"))
    ]
    sources_used = [b.get("url", "") for b in bullets if b.get("url")]
    file_path = ""
    if save:
        out_dir = workspace_root() / "research"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-z0-9_]+", "_", topic.lower())[:50]
        fp = out_dir / f"research_{safe}.md"
        lines_src = "\n".join(
            f"- [{b.get('title', '')}]({b.get('url')})" if b.get("url") else f"- {b.get('title', '')}"
            for b in bullets
        )
        fp.write_text(
            f"# Research Report: {topic}\n\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"{report}\n\n## Sources\n{lines_src}\n",
            encoding="utf-8",
        )
        file_path = str(fp)
    return {
        "report": report,
        "summary": summary,
        "key_facts": key_facts[:15] if key_facts else [summary[:200]],
        "sources_used": sources_used,
        "sources_found": len(bullets),
        "word_count": word_count,
        "success": word_count > 200,
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


# Backwards compatibility for tests / imports
async def tavily_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    return await smart_search(query, limit)
