"""
tools/wordpress.py — WordPress REST API (Application Passwords).
"""
from __future__ import annotations

import base64
from typing import Any

import httpx

from config import settings

TIMEOUT = 45.0


def _base_url() -> str:
    u = (settings.wordpress_site_url or "").strip().rstrip("/")
    if not u:
        raise RuntimeError("wordpress_site_url is not configured")
    return f"{u}/wp-json/wp/v2"


def _auth_header() -> str:
    user = (settings.wordpress_username or "").strip()
    pw = (settings.wordpress_app_password or "").strip()
    if not user or not pw:
        raise RuntimeError("wordpress_username / wordpress_app_password required")
    raw = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {raw}"


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "create_post": _create_post,
        "update_post": _update_post,
        "get_posts": _get_posts,
        "create_page": _create_page,
    }
    fn = dispatch.get(action)
    if not fn:
        raise ValueError(f"Unknown wordpress action: {action}. Available: {list(dispatch)}")
    return await fn(params)


async def _create_post(p: dict[str, Any]) -> dict[str, Any]:
    title = p.get("title", "")
    content = p.get("content", "")
    status = p.get("status", "draft")
    payload: dict[str, Any] = {"title": title, "content": content, "status": status}
    cats = p.get("categories")
    if isinstance(cats, list):
        payload["categories"] = cats
    tags = p.get("tags")
    if isinstance(tags, list):
        payload["tags"] = tags
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{_base_url()}/posts",
            headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            json=payload,
        )
    r.raise_for_status()
    data = r.json()
    pid = data.get("id")
    link = data.get("link", "")
    return {"post_id": pid, "url": link}


async def _update_post(p: dict[str, Any]) -> dict[str, Any]:
    post_id = int(p["post_id"])
    payload = {}
    if p.get("title"):
        payload["title"] = p["title"]
    if p.get("content"):
        payload["content"] = p["content"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{_base_url()}/posts/{post_id}",
            headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            json=payload,
        )
    r.raise_for_status()
    return r.json()


async def _get_posts(p: dict[str, Any]) -> dict[str, Any]:
    status = p.get("status", "publish")
    limit = min(int(p.get("limit") or 10), 100)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(
            f"{_base_url()}/posts",
            headers={"Authorization": _auth_header()},
            params={"status": status, "per_page": limit},
        )
    r.raise_for_status()
    js = r.json()
    return {"posts": js if isinstance(js, list) else [], "count": len(js) if isinstance(js, list) else 0}


async def _create_page(p: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "title": p.get("title", ""),
        "content": p.get("content", ""),
        "status": p.get("status", "draft"),
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{_base_url()}/pages",
            headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
            json=payload,
        )
    r.raise_for_status()
    data = r.json()
    return {"page_id": data.get("id"), "url": data.get("link", "")}
