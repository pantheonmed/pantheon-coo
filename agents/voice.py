"""
agents/voice.py — OpenAI Whisper (transcription) + TTS for voice interface.
"""
from __future__ import annotations

from typing import Optional

import httpx

from config import settings


def _audio_filename_and_mime(mime_type: str) -> tuple[str, str]:
    mt = (mime_type or "audio/ogg").split(";")[0].strip().lower()
    if "mpeg" in mt or "mp3" in mt:
        return "audio.mp3", "audio/mpeg"
    if "wav" in mt:
        return "audio.wav", "audio/wav"
    if "mp4" in mt or "m4a" in mt:
        return "audio.m4a", mt if "/" in mt else "audio/mp4"
    if "webm" in mt:
        return "audio.webm", "audio/webm"
    return "audio.ogg", mt if "/" in mt else "audio/ogg"


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    language: Optional[str] = None,
) -> str:
    """
    Send audio to OpenAI Whisper API.
    Supports: ogg, mp3, mp4, wav, webm (via mime_type).
    """
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for Whisper transcription")

    name, content_type = _audio_filename_and_mime(mime_type)
    model = getattr(settings, "openai_whisper_model", None) or "whisper-1"

    data = {"model": model}
    if language:
        data["language"] = language

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (name, audio_bytes, content_type)},
            data=data,
        )
    r.raise_for_status()
    body = r.json()
    return (body.get("text") or "").strip()


async def text_to_speech(text: str) -> bytes:
    """
    Convert text to speech using OpenAI TTS (MP3 bytes).
    Voice: nova (friendly female voice).
    """
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for TTS")

    payload = {
        "model": "tts-1",
        "voice": "nova",
        "input": (text or "")[:4096],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    r.raise_for_status()
    return r.content
