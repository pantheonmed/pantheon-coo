"""
telegram_bot.py — Telegram Bot API webhook (httpx only).

Include in main.py:
  from telegram_bot import router as telegram_router
  app.include_router(telegram_router)

Webhook URL: POST /webhook/telegram
Setup: GET /webhook/telegram/setup?url=<public_https_url>
Optional: set TELEGRAM_WEBHOOK_SECRET and pass the same value as
X-Telegram-Bot-Api-Secret-Token when configuring setWebhook (secret_token).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/webhook", tags=["telegram"])

TELEGRAM_API = "https://api.telegram.org"


def _cfg():
    from config import settings
    return settings


def _verify_secret(request: Request) -> None:
    cfg = _cfg()
    expected = (getattr(cfg, "telegram_webhook_secret", None) or "").strip()
    if not expected:
        return
    got = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if got != expected:
        raise HTTPException(403, "Invalid Telegram webhook secret")


def _parse_update(body: dict[str, Any]) -> dict[str, Any]:
    """
    Returns keys: chat_id (str|None), text, voice_file_id, audio_file_id, mime_type.
    """
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return {"chat_id": None}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return {"chat_id": None}
    text_raw = msg.get("text")
    text = text_raw.strip() if isinstance(text_raw, str) else ""
    voice = msg.get("voice") if isinstance(msg.get("voice"), dict) else {}
    audio = msg.get("audio") if isinstance(msg.get("audio"), dict) else {}
    vf = voice.get("file_id")
    af = audio.get("file_id")
    mime = "audio/ogg"
    if vf and isinstance(voice, dict):
        mime = voice.get("mime_type") or mime
    elif af and isinstance(audio, dict):
        mime = audio.get("mime_type") or mime
    return {
        "chat_id": str(chat_id),
        "text": text,
        "voice_file_id": vf,
        "audio_file_id": af,
        "mime_type": mime,
    }


async def _download_telegram_file(file_id: str) -> bytes:
    token = (_cfg().telegram_bot_token or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.get(
            f"{TELEGRAM_API}/bot{token}/getFile",
            params={"file_id": file_id},
        )
        r.raise_for_status()
        info = r.json().get("result") or {}
        path = info.get("file_path")
        if not path:
            raise RuntimeError("No file_path from Telegram getFile")
        u = f"https://api.telegram.org/file/bot{token}/{path}"
        r2 = await client.get(u)
        r2.raise_for_status()
        return r2.content


async def _handle_user_voice(chat_id: str, file_id: str, mime_type: str) -> None:
    cfg = _cfg()
    if not getattr(cfg, "voice_enabled", False) or not (cfg.openai_api_key or "").strip():
        await _send_raw(
            chat_id,
            "Voice messages need VOICE_ENABLED=true and OPENAI_API_KEY on the server.",
        )
        return
    try:
        raw = await _download_telegram_file(file_id)
        from agents.voice import transcribe_audio

        text = await transcribe_audio(raw, mime_type)
    except Exception as e:
        await _send_raw(chat_id, f"Could not transcribe: {e!s}"[:500])
        return
    text = (text or "").strip()
    if not text:
        await _send_raw(chat_id, "Empty transcription.")
        return
    await _handle_user_text(chat_id, text)


HELP_EXAMPLES = [
    "Summarize the last 5 tasks in one paragraph",
    "Create a CSV of sample sales data and save to /tmp/pantheon_v2/sales.csv",
    "Check disk usage and list files older than 7 days in workspace",
    "Write a short status email draft for stakeholders",
    "List running processes sorted by memory usage",
]


@router.post("/telegram")
async def receive_telegram(request: Request, background_tasks: BackgroundTasks):
    _verify_secret(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    parsed = _parse_update(body)
    chat_id = parsed.get("chat_id")
    if not chat_id:
        return {"ok": True}

    vf = parsed.get("voice_file_id")
    af = parsed.get("audio_file_id")
    if vf or af:
        fid = vf or af
        mt = str(parsed.get("mime_type") or "audio/ogg")
        background_tasks.add_task(_handle_user_voice, chat_id, fid, mt)
        return {"ok": True}

    t = (parsed.get("text") or "").strip()
    if t.startswith("/start"):
        welcome = (
            "Welcome to Pantheon COO! Send me any task in plain English."
        )
        await _send_raw(chat_id, welcome)
        return {"ok": True}

    if t.startswith("/help"):
        lines = ["Capabilities — example commands:", ""] + [f"• {ex}" for ex in HELP_EXAMPLES]
        await _send_raw(chat_id, "\n".join(lines))
        return {"ok": True}

    if t.startswith("/status"):
        await _send_status(chat_id)
        return {"ok": True}

    if not t:
        return {"ok": True}

    background_tasks.add_task(_handle_user_text, chat_id, t)
    return {"ok": True}


async def _send_raw(chat_id: str, text: str) -> None:
    token = (_cfg().telegram_bot_token or "").strip()
    if not token:
        return
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text[:4096]})


async def _send_status(chat_id: str) -> None:
    import memory.store as store

    rows = await store.list_tasks_by_telegram_chat(chat_id, limit=3)
    if not rows:
        await _send_raw(chat_id, "No tasks yet for this chat.")
        return
    lines = ["Last tasks:"]
    for r in rows:
        g = (r.get("goal") or r.get("command") or "")[:50]
        lines.append(f"• {r.get('task_id', '')[:8]}… — {r.get('status')} — {g}")
    await _send_raw(chat_id, "\n".join(lines))


async def _handle_user_text(chat_id: str, command: str) -> None:
    import memory.store as store
    import orchestrator

    task_id = str(uuid.uuid4())
    preview = command[:60] + ("…" if len(command) > 60 else "")
    await _send_raw(
        chat_id,
        f"⚙️ Processing: {preview}\nTask ID: {task_id[:8]}",
    )
    await store.create_task(
        task_id,
        command,
        source="telegram",
        telegram_chat_id=chat_id,
    )
    await orchestrator.run(
        task_id=task_id,
        command=command,
        context={"telegram_chat_id": chat_id, "source": "telegram"},
        dry_run=False,
    )


@router.get("/telegram/setup")
async def setup_telehook(
    url: str = Query(..., description="Public HTTPS URL for POST /webhook/telegram"),
    secret: str = Query("", description="Optional; must match TELEGRAM_WEBHOOK_SECRET if set"),
):
    """Register Telegram webhook (call once after deployment)."""
    cfg = _cfg()
    token = (cfg.telegram_bot_token or "").strip()
    if not token:
        raise HTTPException(503, "TELEGRAM_BOT_TOKEN is not configured")

    ws = (getattr(cfg, "telegram_webhook_secret", None) or "").strip()
    if ws and secret != ws:
        raise HTTPException(403, "Invalid secret query param")

    api = f"{TELEGRAM_API}/bot{token}/setWebhook"
    payload: dict[str, Any] = {"url": url}
    if ws:
        payload["secret_token"] = ws

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(api, json=payload)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if not r.is_success:
        raise HTTPException(502, f"Telegram API error: {data}")
    return JSONResponse(data)
