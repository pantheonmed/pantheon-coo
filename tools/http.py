"""
tools/http.py — HTTP client tool (Phase 2)

Supported actions:
  get           → HTTP GET
  post          → HTTP POST (JSON or raw body)
  put           → HTTP PUT
  delete        → HTTP DELETE
  send_webhook  → POST with optional secret header
"""
from typing import Any
import httpx

TIMEOUT = 30


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "get":          _get,
        "post":         _post,
        "put":          _put,
        "delete":       _delete,
        "send_webhook": _webhook,
    }
    fn = dispatch.get(action)
    if fn is None:
        raise ValueError(f"Unknown HTTP action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)


async def _get(p: dict) -> dict:
    async with httpx.AsyncClient(timeout=p.get("timeout", TIMEOUT)) as c:
        r = await c.get(p["url"], headers=p.get("headers", {}), params=p.get("params", {}))
    return _fmt(r)


async def _post(p: dict) -> dict:
    async with httpx.AsyncClient(timeout=p.get("timeout", TIMEOUT)) as c:
        kw: dict = {"headers": p.get("headers", {})}
        if "json" in p:
            kw["json"] = p["json"]
        elif "body" in p:
            kw["content"] = p["body"]
        r = await c.post(p["url"], **kw)
    return _fmt(r)


async def _put(p: dict) -> dict:
    async with httpx.AsyncClient(timeout=p.get("timeout", TIMEOUT)) as c:
        r = await c.put(p["url"], headers=p.get("headers", {}), json=p.get("json", {}))
    return _fmt(r)


async def _delete(p: dict) -> dict:
    async with httpx.AsyncClient(timeout=p.get("timeout", TIMEOUT)) as c:
        r = await c.delete(p["url"], headers=p.get("headers", {}))
    return _fmt(r)


async def _webhook(p: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if p.get("secret_header") and p.get("secret_value"):
        headers[p["secret_header"]] = p["secret_value"]
    async with httpx.AsyncClient(timeout=p.get("timeout", TIMEOUT)) as c:
        r = await c.post(p["url"], json=p.get("payload", {}), headers=headers)
    return _fmt(r)


def _fmt(r: httpx.Response) -> dict:
    body: Any = r.text
    if "application/json" in r.headers.get("content-type", ""):
        try:
            body = r.json()
        except Exception:
            pass
    return {"status_code": r.status_code, "ok": r.is_success, "body": body, "url": str(r.url)}
