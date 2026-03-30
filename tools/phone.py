"""
tools/phone.py — Twilio outbound calls (TwiML Say), SMS, conference, recording, callbacks.
"""
from __future__ import annotations

import html
import uuid
from typing import Any

import httpx

from config import settings

_TWILIO_BASE = "https://api.twilio.com/2010-04-01/Accounts"


def _voice_attrs(voice: str, language: str) -> tuple[str, str]:
    v = (voice or "woman").strip().lower()
    lang = (language or "en-IN").strip()
    if lang.startswith("hi"):
        polly = "Polly.Kajal" if v == "woman" else "Polly.Madhur"
        return polly, "hi-IN"
    if lang.startswith("en-US") or lang == "en-US":
        polly = "Polly.Joanna" if v == "woman" else "Polly.Matthew"
        return polly, "en-US"
    polly = "Polly.Aditi" if v == "woman" else "Polly.Prabhakar"
    return polly, "en-IN"


def _twiml_say(message: str, voice: str, language: str) -> str:
    polly, lang = _voice_attrs(voice, language)
    safe = html.escape(message or "", quote=True)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Say voice=\"{polly}\" language=\"{lang}\">{safe}</Say></Response>"
    )


def _twiml_conference(conf_name: str) -> str:
    safe = html.escape(conf_name or "room", quote=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Dial><Conference beep="false">{safe}</Conference></Dial></Response>'
    )


async def _make_call(p: dict[str, Any]) -> dict[str, Any]:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio is not configured (twilio_account_sid / twilio_auth_token).")
    if not settings.twilio_phone_number:
        raise ValueError("twilio_phone_number is not configured.")
    to_number = str(p.get("to_number", "")).strip()
    message = str(p.get("message", "")).strip()
    if not to_number or not message:
        raise ValueError("to_number and message are required.")
    voice = str(p.get("voice") or "woman")
    language = str(p.get("language") or "en-IN")
    twiml = _twiml_say(message, voice, language)
    url = f"{_TWILIO_BASE}/{settings.twilio_account_sid}/Calls.json"
    data = {"To": to_number, "From": settings.twilio_phone_number, "Twiml": twiml}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            url,
            data=data,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
    r.raise_for_status()
    body = r.json()
    return {"call_sid": body.get("sid", ""), "status": body.get("status", "")}


async def _send_sms(p: dict[str, Any]) -> dict[str, Any]:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio is not configured.")
    if not settings.twilio_phone_number:
        raise ValueError("twilio_phone_number is not configured.")
    to_number = str(p.get("to_number", "")).strip()
    message = str(p.get("message", "")).strip()
    if not to_number or not message:
        raise ValueError("to_number and message are required.")
    url = f"{_TWILIO_BASE}/{settings.twilio_account_sid}/Messages.json"
    data = {"To": to_number, "From": settings.twilio_phone_number, "Body": message}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            url,
            data=data,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
    r.raise_for_status()
    body = r.json()
    return {"message_sid": body.get("sid", ""), "status": body.get("status", "")}


async def _get_call_status(p: dict[str, Any]) -> dict[str, Any]:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio is not configured.")
    call_sid = str(p.get("call_sid", "")).strip()
    if not call_sid:
        raise ValueError("call_sid is required.")
    url = f"{_TWILIO_BASE}/{settings.twilio_account_sid}/Calls/{call_sid}.json"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token))
    r.raise_for_status()
    body = r.json()
    return {
        "status": body.get("status", ""),
        "duration": body.get("duration"),
        "direction": body.get("direction", ""),
    }


async def _start_conference(p: dict[str, Any]) -> dict[str, Any]:
    """Dial participants into a Twilio Conference (same conference name)."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio is not configured.")
    if not settings.twilio_phone_number:
        raise ValueError("twilio_phone_number is not configured.")
    participants = p.get("participants") or []
    if not isinstance(participants, list) or not participants:
        raise ValueError("participants must be a non-empty list of E.164 numbers.")
    topic = str(p.get("topic", "")).strip()
    conf_name = f"pantheon-{uuid.uuid4().hex[:16]}"
    twiml = _twiml_conference(conf_name)
    url = f"{_TWILIO_BASE}/{settings.twilio_account_sid}/Calls.json"
    call_sids: list[str] = []
    async with httpx.AsyncClient(timeout=90.0) as client:
        for num in participants:
            to_number = str(num).strip()
            if not to_number:
                continue
            data = {"To": to_number, "From": settings.twilio_phone_number, "Twiml": twiml}
            r = await client.post(
                url,
                data=data,
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
            r.raise_for_status()
            call_sids.append(str(r.json().get("sid", "")))
    return {
        "conference_name": conf_name,
        "topic": topic,
        "participant_call_sids": call_sids,
        "status": "dialing",
    }


async def _record_call(p: dict[str, Any]) -> dict[str, Any]:
    """Start recording on an active call (ensure callee consent per regulations)."""
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise ValueError("Twilio is not configured.")
    call_sid = str(p.get("call_sid", "")).strip()
    if not call_sid:
        raise ValueError("call_sid is required.")
    url = f"{_TWILIO_BASE}/{settings.twilio_account_sid}/Calls/{call_sid}/Recordings.json"
    data = {"RecordingChannels": "dual"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            url,
            data=data,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )
    r.raise_for_status()
    body = r.json()
    return {
        "recording_sid": body.get("sid", ""),
        "status": body.get("status", ""),
        "consent_warning": "Recording requires consent where required by law.",
    }


async def _transcribe_call(p: dict[str, Any]) -> dict[str, Any]:
    recording_url = str(p.get("recording_url", "")).strip()
    if not recording_url:
        raise ValueError("recording_url is required.")
    from agents.voice import transcribe_audio

    auth = None
    if "twilio.com" in recording_url and settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        r = await client.get(recording_url, auth=auth)
    r.raise_for_status()
    audio = r.content
    mt = r.headers.get("content-type", "audio/mpeg")
    text = await transcribe_audio(audio, mime_type=mt)
    return {"transcript": text, "bytes": len(audio)}


async def _schedule_callback(p: dict[str, Any]) -> dict[str, Any]:
    to_number = str(p.get("to_number", "")).strip()
    callback_time = str(p.get("callback_time", "")).strip()
    message = str(p.get("message", "")).strip()
    if not to_number or not callback_time or not message:
        raise ValueError("to_number, callback_time, and message are required.")
    cmd = (
        f"Use the phone tool make_call to call {to_number} "
        f"with message: {message}"
    )
    from scheduler import insert_oneshot_schedule

    res = await insert_oneshot_schedule(
        name=f"[oneshot] Callback {to_number}",
        command=cmd,
        run_at_iso=callback_time,
    )
    return {"scheduled": True, **res}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "make_call": _make_call,
        "send_sms": _send_sms,
        "get_call_status": _get_call_status,
        "start_conference": _start_conference,
        "record_call": _record_call,
        "transcribe_call": _transcribe_call,
        "schedule_callback": _schedule_callback,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown phone action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
