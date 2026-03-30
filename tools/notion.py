"""
tools/notion.py — Notion API v1 (pages, search, database rows).
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from config import settings

BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict[str, str]:
    if not settings.notion_api_key:
        raise ValueError("NOTION_API_KEY is not configured.")
    return {
        "Authorization": f"Bearer {settings.notion_api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _markdown_to_blocks(md: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for para in re.split(r"\n{2,}", (md or "").strip() or "(empty)"):
        line = para.strip()
        if line.startswith("# "):
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[2:][:2000]}}]},
                }
            )
        else:
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:2000]}}]},
                }
            )
    return blocks[:100]


async def _create_page(p: dict[str, Any]) -> dict[str, Any]:
    parent_id = str(p.get("parent_page_id", "")).strip()
    title = str(p.get("title", ""))
    content = str(p.get("content", ""))
    body = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title[:2000]}}]},
        },
        "children": _markdown_to_blocks(content),
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/pages", json=body, headers=_headers())
        r.raise_for_status()
        data = r.json()
    return {"page_id": data.get("id", ""), "url": data.get("url", "")}


async def _update_page(p: dict[str, Any]) -> dict[str, Any]:
    page_id = str(p.get("page_id", "")).strip()
    content = str(p.get("content", ""))
    r2 = await _append_to_page({"page_id": page_id, "content": content})
    return {"page_id": page_id, "updated": True, "appended": r2.get("appended", 0)}


async def _read_page(p: dict[str, Any]) -> dict[str, Any]:
    page_id = str(p.get("page_id", "")).strip()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{BASE}/pages/{page_id}", headers=_headers())
        r.raise_for_status()
        page = r.json()
        br = await client.get(
            f"{BASE}/blocks/{page_id}/children",
            headers=_headers(),
            params={"page_size": 100},
        )
        br.raise_for_status()
        blocks = br.json().get("results", [])
    title = ""
    props = page.get("properties") or {}
    for v in props.values():
        if isinstance(v, dict) and v.get("type") == "title":
            arr = v.get("title") or []
            if arr:
                title = arr[0].get("plain_text") or ""
            break
    parts: list[str] = []
    for b in blocks:
        t = b.get("type")
        if t == "paragraph":
            pt = b.get("paragraph", {}).get("rich_text", [])
            parts.append("".join(x.get("plain_text", "") for x in pt))
        elif t and t.startswith("heading"):
            ht = b.get(t, {}).get("rich_text", [])
            parts.append("# " + "".join(x.get("plain_text", "") for x in ht))
    return {
        "title": title,
        "content": "\n\n".join(parts),
        "last_edited": page.get("last_edited_time", ""),
    }


async def _create_database_entry(p: dict[str, Any]) -> dict[str, Any]:
    db_id = str(p.get("database_id", "")).strip()
    props = p.get("properties") or {}
    body = {"parent": {"database_id": db_id}, "properties": props}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/pages", json=body, headers=_headers())
        r.raise_for_status()
        data = r.json()
    return {"entry_id": data.get("id", ""), "url": data.get("url", "")}


async def _search_pages(p: dict[str, Any]) -> list[dict[str, Any]]:
    q = str(p.get("query", ""))
    limit = min(int(p.get("limit") or 10), 25)
    body = {"query": q, "page_size": limit}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/search", json=body, headers=_headers())
        r.raise_for_status()
        data = r.json()
    out: list[dict[str, Any]] = []
    for it in data.get("results", []):
        if it.get("object") != "page":
            continue
        title = ""
        for v in (it.get("properties") or {}).values():
            if isinstance(v, dict) and v.get("type") == "title":
                arr = v.get("title") or []
                if arr:
                    title = arr[0].get("plain_text", "")
                break
        out.append(
            {
                "title": title or "(untitled)",
                "page_id": it.get("id", ""),
                "url": it.get("url", ""),
                "last_edited": it.get("last_edited_time", ""),
            }
        )
    return out


async def _append_to_page(p: dict[str, Any]) -> dict[str, Any]:
    page_id = str(p.get("page_id", "")).strip()
    content = str(p.get("content", ""))
    children = _markdown_to_blocks(content)
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.patch(
            f"{BASE}/blocks/{page_id}/children",
            json={"children": children},
            headers=_headers(),
        )
        r.raise_for_status()
    return {"page_id": page_id, "appended": len(children)}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "create_page": _create_page,
        "update_page": _update_page,
        "read_page": _read_page,
        "create_database_entry": _create_database_entry,
        "search_pages": _search_pages,
        "append_to_page": _append_to_page,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown notion action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
