"""
webhook_sender.py — deliver outbound webhooks on task completion.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime

import httpx

import memory.store as store


async def fire_webhook(user_id: str, event_type: str, payload: dict) -> None:
    if not user_id:
        return
    subs = await store.list_active_webhooks_for_user(user_id, event_type)
    for sub in subs:
        asyncio.create_task(_deliver_one(sub, event_type, payload))


async def _deliver_one(sub: dict, event_type: str, payload: dict) -> None:
    wid = sub["webhook_id"]
    url = sub["url"]
    secret = sub["secret"]
    body_obj = {
        "event": event_type,
        "data": payload,
        "ts": datetime.utcnow().isoformat(),
    }
    body = json.dumps(body_obj, separators=(",", ":"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Pantheon-Signature": f"sha256={sig}",
    }
    await _post_with_retry(wid, url, body, headers, event_type)


async def _post_with_retry(
    webhook_id: str,
    url: str,
    body: str,
    headers: dict,
    event_type: str,
) -> None:
    async def attempt() -> tuple[int, bool]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, content=body, headers=headers)
            ok = 200 <= r.status_code < 300
            await store.append_webhook_log(
                webhook_id, event_type, body, r.status_code, 1 if ok else 0
            )
            if r.status_code >= 500 or not ok:
                await store.increment_webhook_failure(webhook_id)
            return r.status_code, ok
        except Exception:
            await store.append_webhook_log(webhook_id, event_type, body, None, 0)
            await store.increment_webhook_failure(webhook_id)
            return -1, False

    code, ok = await attempt()
    if not ok:
        await asyncio.sleep(5)
        await attempt()
