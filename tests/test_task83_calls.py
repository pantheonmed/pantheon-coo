"""Task 83 — Call agent, phone tool extensions, call templates."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import memory.store as store
from agents.call_agent import CallAgent, CallScriptOutput
from security.sandbox import SecurityError, validate_phone_number
from tools import phone as phone_tool
from templates import TEMPLATES


@pytest.mark.asyncio
async def test_schedule_callback_creates_scheduler_entry():
    await store.init()
    from datetime import datetime, timedelta, timezone

    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0).isoformat()
    res = await phone_tool.execute(
        "schedule_callback",
        {
            "to_number": "+919876543210",
            "callback_time": when,
            "message": "Follow up on quotation",
        },
    )
    assert res.get("schedule_id")
    assert res.get("next_run_at")


@pytest.mark.asyncio
async def test_transcribe_call_uses_whisper_mock():
    fake_audio = b"fake mp3"

    class _Resp:
        content = fake_audio
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            pass

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *a, **k):
            return _Resp()

    with patch("tools.phone.httpx.AsyncClient", return_value=_Client()):
        with patch("agents.voice.transcribe_audio", new_callable=AsyncMock) as tr:
            tr.return_value = "Hello from the call."
            out = await phone_tool.execute(
                "transcribe_call",
                {"recording_url": "https://example.com/rec.mp3"},
            )
    assert out.get("transcript") == "Hello from the call."


@pytest.mark.asyncio
async def test_call_agent_generates_script_with_key_points(mock_claude_api):
    agent = CallAgent()
    with patch.object(
        CallAgent,
        "_call_claude_async",
        new_callable=AsyncMock,
        return_value=CallScriptOutput(
            script="Hello, this is the COO assistant calling about pricing."
        ),
    ):
        script = await agent.generate_call_script(
            purpose="Get quote",
            recipient_name="Ravi",
            key_points=["Ask for MOQ", "Delivery to Chennai"],
        )
    assert "COO assistant" in script or "pricing" in script.lower() or "quote" in script.lower()


def test_call_templates_variables():
    tpls = TEMPLATES
    by_id = {t["id"]: t for t in tpls}
    assert set(by_id["call_supplier"]["variables"]) == {
        "phone_number",
        "contact_name",
        "product",
        "quantity",
    }
    assert set(by_id["call_followup"]["variables"]) == {"phone_number", "date", "product"}
    assert set(by_id["medical_appointment"]["variables"]) == {
        "doctor_name",
        "phone_number",
        "hospital",
        "dates",
    }


def test_phone_number_validation_sandbox():
    validate_phone_number("+919876543210")
    with pytest.raises(SecurityError):
        validate_phone_number("+9991234567890")


def test_templates_list_includes_call_supplier():
    ids = {t["id"] for t in TEMPLATES}
    assert "call_supplier" in ids
    assert "medical_appointment" in ids
