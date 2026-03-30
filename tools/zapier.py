"""
tools/zapier.py — Zapier webhooks & automation helpers.
"""
from __future__ import annotations

from typing import Any

import httpx

from security.sandbox import SecurityError, validate_security_target_url

TIMEOUT = 30.0


async def execute(action: str, params: dict[str, Any]) -> Any:
    if action == "send_to_webhook":
        return await _send_to_webhook(params)
    if action == "trigger_zap":
        return await _trigger_zap(params)
    raise ValueError(f"Unknown zapier action: {action}. Use: send_to_webhook, trigger_zap")


async def _send_to_webhook(p: dict[str, Any]) -> dict[str, Any]:
    url = (p.get("webhook_url") or "").strip()
    if not url:
        raise ValueError("webhook_url is required")
    validate_security_target_url(url)
    method = (p.get("method") or "POST").upper()
    data = p.get("data") if isinstance(p.get("data"), dict) else {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        if method == "GET":
            r = await c.get(url, params=data)
        else:
            r = await c.post(url, json=data)
    return {"success": r.is_success, "response_code": r.status_code, "body_preview": (r.text or "")[:500]}


async def _trigger_zap(p: dict[str, Any]) -> dict[str, Any]:
    zap_url = (p.get("zap_webhook_url") or "").strip()
    if not zap_url:
        raise ValueError("zap_webhook_url is required")
    validate_security_target_url(zap_url)
    trigger_data = p.get("trigger_data") if isinstance(p.get("trigger_data"), dict) else {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(zap_url, json=trigger_data)
    return {"success": r.is_success, "response_code": r.status_code}
