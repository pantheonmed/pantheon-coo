"""
notifications.py — outbound notifications (Telegram, etc.)
"""
from __future__ import annotations

import httpx

from config import settings

TELEGRAM_API = "https://api.telegram.org"


async def send_telegram(chat_id: str, text: str) -> bool:
    """Send a plain-text message via Telegram Bot API."""
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return False
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                url,
                json={"chat_id": chat_id, "text": (text or "")[:4096]},
            )
        return r.is_success
    except Exception:
        return False
