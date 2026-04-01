"""
whatsapp.py — Meta WhatsApp Cloud API webhook (Phase 2)

Setup in Meta Developer Console:
  1. Create a Meta App → Add WhatsApp product
  2. Webhook URL:    https://your-domain.com/webhook/whatsapp
  3. Verify Token:  set WHATSAPP_VERIFY_TOKEN in .env (any secret string)
  4. Subscribe to:  messages

Required .env vars:
  WHATSAPP_VERIFY_TOKEN     ← your secret string
  WHATSAPP_ACCESS_TOKEN     ← from Meta → WhatsApp → API Setup
  WHATSAPP_PHONE_NUMBER_ID  ← from Meta → WhatsApp → API Setup

Include this router in main.py:
  from whatsapp import router as wa_router
  app.include_router(wa_router)
"""
import json
import uuid
import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/webhook", tags=["whatsapp"])

WA_API = "https://graph.facebook.com/v19.0"


# ─────────────────────────────────────────────────────────────────────────────
# Lazy settings access (avoids import-time errors if vars not set)
# ─────────────────────────────────────────────────────────────────────────────

def _cfg():
    from config import settings
    return settings


class _Msg(BaseModel):
    from_number: str
    message_id: str
    text: str
    timestamp: str
    phone_number_id: str
    is_voice: bool = False
    media_id: Optional[str] = None
    mime_type: str = "audio/ogg"
    order_payload: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# Webhook verification (GET)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/whatsapp")
async def verify(request: Request):
    """Meta sends a GET to verify the webhook. Echo the challenge."""
    p = request.query_params
    cfg = _cfg()
    verify_token = getattr(cfg, "whatsapp_verify_token", "")
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == verify_token:
        print("[WhatsApp] Webhook verified ✓")
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403, "Webhook verification failed")


# ─────────────────────────────────────────────────────────────────────────────
# Inbound message (POST)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def receive(request: Request, background_tasks: BackgroundTasks):
    """Receive a WhatsApp message and dispatch it to the COO agent loop."""
    raw_body = await request.body()

    # Verify HMAC signature if app secret is configured
    sig = request.headers.get("X-Hub-Signature-256", "")
    from security.auth import verify_whatsapp_signature
    if not verify_whatsapp_signature(raw_body, sig):
        raise HTTPException(403, "Invalid webhook signature")

    try:
        import json as _json
        body = _json.loads(raw_body)
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    msg = _parse(body)
    if msg is None:
        return {"status": "ok", "action": "ignored"}

    if msg.order_payload is not None:
        background_tasks.add_task(handle_order, msg.order_payload)
        return {"status": "ok", "action": "order"}

    preview = (msg.text[:80] if msg.text else f"[audio id={msg.media_id}]")
    print(f"[WhatsApp] {msg.from_number}: {preview}")
    background_tasks.add_task(_handle, msg)
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Outbound reply
# ─────────────────────────────────────────────────────────────────────────────

async def _download_whatsapp_media(media_id: str) -> bytes:
    """GET media metadata then download binary from WhatsApp CDN."""
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN not configured")

    async with httpx.AsyncClient(timeout=60) as c:
        meta = await c.get(
            f"{WA_API}/{media_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        meta.raise_for_status()
        url = (meta.json() or {}).get("url")
        if not url:
            raise RuntimeError("No media URL in WhatsApp response")
        dl = await c.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        dl.raise_for_status()
        return dl.content


async def _upload_whatsapp_audio(audio_bytes: bytes, mime: str = "audio/mpeg") -> str:
    """Upload audio bytes; returns media id for sending."""
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    phone_id = getattr(cfg, "whatsapp_phone_number_id", "")
    if not token or not phone_id:
        raise RuntimeError("WhatsApp credentials missing")

    fname = "reply.mp3" if "mpeg" in mime or "mp3" in mime else "reply.ogg"
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            f"{WA_API}/{phone_id}/media",
            headers={"Authorization": f"Bearer {token}"},
            data={"messaging_product": "whatsapp", "type": "audio"},
            files={"file": (fname, audio_bytes, mime)},
        )
        r.raise_for_status()
        mid = (r.json() or {}).get("id")
        if not mid:
            raise RuntimeError("WhatsApp media upload returned no id")
        return mid


async def send_audio(to: str, audio_bytes: bytes, mime: str = "audio/mpeg") -> dict:
    """Send an audio message (voice reply)."""
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    phone_id = getattr(cfg, "whatsapp_phone_number_id", "")
    if not token or not phone_id:
        print("[WhatsApp] No credentials — skipped audio reply")
        return {"skipped": True}

    mid = await _upload_whatsapp_audio(audio_bytes, mime=mime)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WA_API}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "audio",
                "audio": {"id": mid},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    return r.json()


async def send_catalog(
    to_number: str,
    catalog_id: str,
    body_text: str = "Check out our products!",
) -> dict:
    """Send a WhatsApp catalog message (interactive catalog_message)."""
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    phone_id = getattr(cfg, "whatsapp_phone_number_id", "")
    cid = catalog_id or getattr(cfg, "whatsapp_catalog_id", "") or "default-catalog"
    if not token or not phone_id:
        print("[WhatsApp] No credentials — skipped catalog send")
        return {"skipped": True, "type": "catalog_message"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WA_API}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "catalog_message",
                    "body": {"text": body_text[:1024]},
                    "action": {
                        "name": "catalog_message",
                        "parameters": {"catalog_id": cid},
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    return r.json()


async def send_product(
    to_number: str,
    catalog_id: str,
    product_retailer_id: str,
) -> dict:
    """Send a single product card from a catalog."""
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    phone_id = getattr(cfg, "whatsapp_phone_number_id", "")
    cid = catalog_id or getattr(cfg, "whatsapp_catalog_id", "")
    if not token or not phone_id:
        return {"skipped": True}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{WA_API}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "interactive",
                "interactive": {
                    "type": "product",
                    "body": {"text": "Product"},
                    "action": {
                        "catalog_id": cid,
                        "product_retailer_id": product_retailer_id,
                    },
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    return r.json()


async def handle_order(order_data: dict) -> dict:
    """Persist WhatsApp order payload and return extracted commerce fields."""
    import memory.store as store

    items = order_data.get("product_items") or order_data.get("items") or []
    total = float(order_data.get("total") or order_data.get("estimated_total") or 0)
    await store.track_event(
        "whatsapp_order",
        "",
        {
            "items": items,
            "total": total,
            "shipping": order_data.get("shipping_address") or order_data.get("shipping"),
        },
    )
    return {
        "items": items,
        "total": total,
        "shipping_address": order_data.get("shipping_address"),
        "saved": True,
    }


async def send_order_confirmation(
    to_number: str,
    order_id: str,
    items: list,
    total: float,
) -> dict:
    lines = ", ".join(str(i) for i in items[:12])
    body = f"Order {order_id} confirmed. Items: {lines}. Total: {total}"
    return await send(to_number, body)


async def send_shipping_update(
    to_number: str,
    order_id: str,
    status: str,
    tracking_url: str = "",
) -> dict:
    body = f"Order {order_id}: shipping status is {status}."
    if tracking_url:
        body += f" Track: {tracking_url}"
    return await send(to_number, body)


async def send(to: str, text: str) -> dict:
    cfg = _cfg()
    token = getattr(cfg, "whatsapp_access_token", "")
    phone_id = getattr(cfg, "whatsapp_phone_number_id", "")

    if not token or not phone_id:
        print(f"[WhatsApp] No credentials — skipped reply: {text[:60]}")
        return {"skipped": True}

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{WA_API}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text[:4096]},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Agent loop handler (runs in background)
# ─────────────────────────────────────────────────────────────────────────────

async def _handle(msg: _Msg) -> None:
    import memory.store as store
    import orchestrator

    cfg = _cfg()
    voice_on = bool(getattr(cfg, "voice_enabled", False))
    has_openai = bool((getattr(cfg, "openai_api_key", None) or "").strip())

    if msg.media_id:
        if not voice_on or not has_openai:
            await send(
                msg.from_number,
                "Voice notes need VOICE_ENABLED=true and OPENAI_API_KEY in your server .env.",
            )
            return
        try:
            raw_audio = await _download_whatsapp_media(msg.media_id)
            from agents.voice import transcribe_audio

            msg.text = await transcribe_audio(raw_audio, msg.mime_type)
            msg.is_voice = True
        except Exception as e:
            await send(msg.from_number, f"Could not transcribe audio: {e!s}"[:500])
            return

    command = (msg.text or "").strip()
    if not command:
        await send(msg.from_number, "Empty message — send text or a voice note.")
        return

    def _is_self_update_command(txt: str) -> bool:
        t = (txt or "").lower()
        # Hinglish triggers + self-reference
        triggers = ("apne mein", "add karo", "improve karo", "fix karo", "self update", "self-update")
        if not any(x in t for x in triggers):
            return False
        # Must be about COO itself
        self_words = ("pantheon", "coo", "coo os", "dashboard", "backend", "orchestrator", "whatsapp", "admin")
        return any(w in t for w in self_words)

    def _parse_confirm(txt: str) -> tuple[str, str] | None:
        t = (txt or "").strip()
        if not t:
            return None
        low = t.lower()
        if low.startswith("haan "):
            return ("haan", t.split(" ", 1)[1].strip())
        if low.startswith("nahi "):
            return ("nahi", t.split(" ", 1)[1].strip())
        return None

    task_id = str(uuid.uuid4())

    preview = command[:60] + ("…" if len(command) > 60 else "")
    await send(
        msg.from_number,
        f"⚙️ COO processing: \"{preview}\"\nTask: {task_id[:8]}",
    )

    await store.create_task(task_id, command, source="whatsapp")
    conf = _parse_confirm(command)
    if conf:
        decision, token = conf
        try:
            from agents.self_update_agent import SelfUpdateAgent

            res = await SelfUpdateAgent().confirm_and_push(token, decision)
            if res.get("ok") and res.get("pushed"):
                await send(
                    msg.from_number,
                    "✅ Self-update pushed to main.\n"
                    f"Backup branch: {res.get('backup_branch')}\n"
                    f"Commit: {res.get('commit_sha')}\n\n"
                    "Railway will auto-deploy in ~1-2 minutes.",
                )
            elif res.get("ok") and not res.get("pushed"):
                await send(msg.from_number, "Cancelled. No changes were pushed.")
            else:
                await send(msg.from_number, f"Could not confirm/push: {res.get('error')}")
        except Exception as e:
            await send(msg.from_number, f"Self-update confirm error: {e!s}"[:900])
        return

    if _is_self_update_command(command):
        try:
            # Self-update runs in-process; requires GITHUB_TOKEN on server.
            from agents.self_update_agent import SelfUpdateAgent

            await store.log(task_id, "Self-update route detected from WhatsApp.", "info")
            out = await SelfUpdateAgent().prepare_self_update(
                repo=_cfg().self_repo,
                instruction=command,
            )
            if out.get("confirmation_needed"):
                tok = out.get("token", "")
                await store.update_status(
                    task_id,
                    status="done",
                    summary="Self-update prepared. Reply 'haan' to push, or 'nahi' to cancel.",
                    iterations=1,
                )
                await send(
                    msg.from_number,
                    "Self-update prepared.\n\n"
                    f"Files: {', '.join(out.get('files_affected') or [])}\n\n"
                    f"Reply:\n- haan {tok}\n- nahi {tok}\n\n"
                    "I will push to main only after your confirmation.",
                )
            else:
                await store.update_status(
                    task_id,
                    status="failed",
                    summary=str(out.get("error") or "Self-update failed"),
                    iterations=1,
                )
                await send(msg.from_number, f"Self-update failed:\n{out.get('error')}")
        except Exception as e:
            await store.update_status(
                task_id,
                status="failed",
                summary=f"Self-update error: {e}",
                iterations=1,
            )
            await send(msg.from_number, f"Self-update error: {e!s}"[:900])
    else:
        await orchestrator.run(
            task_id=task_id,
            command=command,
            context={
                "from": msg.from_number,
                "source": "whatsapp",
                "whatsapp_voice": msg.is_voice,
            },
            dry_run=False,
        )

    row = await store.get_task(task_id)
    if not row:
        return

    score = row.get("eval_score")
    score_str = f"Score: {score:.2f}" if score is not None else ""
    iterations = row.get("loop_iterations", 0)
    summary = row.get("summary", "")

    status_icon = "✅" if row["status"] == "done" else "⚠️"
    reply = (
        f"{status_icon} *COO Report* (Task {task_id[:8]})\n\n"
        f"{summary}\n\n"
        f"Loop iterations: {iterations}  {score_str}"
    )

    if msg.is_voice and voice_on and has_openai:
        try:
            from agents.voice import text_to_speech

            spoken = f"{summary}\nScore {score_str}. Task {task_id[:8]}."
            mp3 = await text_to_speech(spoken[:3900])
            await send_audio(msg.from_number, mp3, mime="audio/mpeg")
        except Exception:
            await send(msg.from_number, reply)
    else:
        await send(msg.from_number, reply)


# ─────────────────────────────────────────────────────────────────────────────
# Parse inbound webhook payload
# ─────────────────────────────────────────────────────────────────────────────

def _parse(body: dict) -> Optional[_Msg]:
    try:
        value = body["entry"][0]["changes"][0]["value"]
        if "statuses" in value:
            return None
        msgs = value.get("messages", [])
        if not msgs:
            return None
        raw = msgs[0]
        mtype = raw.get("type")
        meta_pid = value["metadata"]["phone_number_id"]

        if mtype == "text":
            return _Msg(
                from_number=raw["from"],
                message_id=raw["id"],
                text=raw["text"]["body"],
                timestamp=raw["timestamp"],
                phone_number_id=meta_pid,
                is_voice=False,
            )

        if mtype == "audio":
            aud = raw.get("audio") or {}
            mid = aud.get("id")
            if not mid:
                return None
            mime = aud.get("mime_type") or "audio/ogg"
            return _Msg(
                from_number=raw["from"],
                message_id=raw["id"],
                text="",
                timestamp=raw["timestamp"],
                phone_number_id=meta_pid,
                is_voice=True,
                media_id=mid,
                mime_type=mime,
            )

        if mtype == "order":
            return _Msg(
                from_number=raw["from"],
                message_id=raw["id"],
                text="",
                timestamp=raw.get("timestamp", ""),
                phone_number_id=meta_pid,
                is_voice=False,
                order_payload=raw.get("order") or raw,
            )

        return None
    except (KeyError, IndexError):
        return None
