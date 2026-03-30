"""
Task 31 — Voice: Whisper transcription, TTS, WhatsApp/Telegram audio, /voice API.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_transcribe_audio_sends_correct_request_format(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")
    monkeypatch.setattr(settings, "openai_whisper_model", "whisper-1")

    captured: dict = {}

    async def fake_post(url, **kwargs):
        captured["url"] = url
        captured["files"] = kwargs.get("files")
        captured["data"] = kwargs.get("data")
        r = MagicMock()
        r.raise_for_status = lambda: None
        r.json = lambda: {"text": " transcribed command "}
        return r

    mock_inst = MagicMock()
    mock_inst.post = AsyncMock(side_effect=fake_post)
    mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
    mock_inst.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_inst):
        from agents.voice import transcribe_audio

        out = await transcribe_audio(b"\x00\x01", "audio/ogg")

    assert out == "transcribed command"
    assert "audio/transcriptions" in captured["url"]
    assert captured["data"]["model"] == "whisper-1"
    assert "file" in captured["files"]


@pytest.mark.asyncio
async def test_text_to_speech_returns_bytes(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")

    async def fake_post(url, **kwargs):
        r = MagicMock()
        r.raise_for_status = lambda: None
        r.content = b"\xff\xfb\x90" + b"mp3fake"
        return r

    mock_inst = MagicMock()
    mock_inst.post = AsyncMock(side_effect=fake_post)
    mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
    mock_inst.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_inst):
        from agents.voice import text_to_speech

        data = await text_to_speech("Hello world")

    assert isinstance(data, bytes)
    assert len(data) > 3


def test_whatsapp_parse_audio_message():
    from whatsapp import _parse

    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "PHONE_ID"},
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": "wamid.123",
                                    "timestamp": "1234567890",
                                    "type": "audio",
                                    "audio": {
                                        "id": "MEDIA_ID_XYZ",
                                        "mime_type": "audio/ogg; codecs=opus",
                                        "voice": True,
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    m = _parse(body)
    assert m is not None
    assert m.media_id == "MEDIA_ID_XYZ"
    assert m.is_voice is True
    assert m.text == ""


def test_voice_transcribe_endpoint_returns_task_id_when_auto_execute(client: TestClient, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    async def fake_transcribe(data, mime):  # noqa: ARG001
        return "run disk check"

    with patch("agents.voice.transcribe_audio", side_effect=fake_transcribe):
        with patch("orchestrator.run", new_callable=AsyncMock):
            r = client.post(
                "/voice/transcribe?auto_execute=true",
                files={"file": ("note.ogg", b"\x00\x01\x02", "audio/ogg")},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "run disk check"
    assert "task_id" in body
    assert len(body["task_id"]) == 36
