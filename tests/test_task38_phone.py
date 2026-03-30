"""Task 38 — Twilio phone + SMS tool + sandbox."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import REGISTRY
from tools import phone as phone_mod


@pytest.mark.asyncio
async def test_make_call_sends_twilio_request(monkeypatch):
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "tok")
    monkeypatch.setattr(settings, "twilio_phone_number", "+15551234567")
    captured = {}

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"sid": "CAabc", "status": "queued"})

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["data"] = kwargs.get("data") or {}
            captured["auth"] = kwargs.get("auth")
            return fake_resp

    with patch("tools.phone.httpx.AsyncClient", return_value=FakeClient()):
        r = await phone_mod.execute(
            "make_call",
            {"to_number": "+919876543210", "message": "Hello from COO", "voice": "woman", "language": "en-IN"},
        )
    assert r["call_sid"] == "CAabc"
    assert r["status"] == "queued"
    assert "Accounts/ACtest/Calls.json" in captured["url"]
    assert captured["data"]["To"] == "+919876543210"
    assert "Twiml" in captured["data"] or "twiml" in {k.lower(): k for k in captured["data"]}
    twiml_key = "Twiml" if "Twiml" in captured["data"] else next(k for k in captured["data"] if k.lower() == "twiml")
    assert "Hello from COO" in captured["data"][twiml_key]


@pytest.mark.asyncio
async def test_send_sms_creates_message(monkeypatch):
    monkeypatch.setattr(settings, "twilio_account_sid", "ACtest")
    monkeypatch.setattr(settings, "twilio_auth_token", "tok")
    monkeypatch.setattr(settings, "twilio_phone_number", "+15551234567")
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"sid": "SMxyz", "status": "queued"})

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, **kwargs):
            self.last_url = url
            self.last_data = kwargs.get("data")
            return fake_resp

    fc = FakeClient()
    with patch("tools.phone.httpx.AsyncClient", return_value=fc):
        r = await phone_mod.execute(
            "send_sms",
            {"to_number": "+919811122233", "message": "Ping"},
        )
    assert r["message_sid"] == "SMxyz"
    assert fc.last_data["Body"] == "Ping"


def test_invalid_phone_blocked_by_sandbox():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.PHONE,
        action="make_call",
        params={"to_number": "+000123", "message": "x"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError):
        validate_step(step)


def test_toolname_phone_enum():
    assert ToolName.PHONE.value == "phone"


def test_phone_in_registry():
    assert ToolName.PHONE in REGISTRY
    assert REGISTRY[ToolName.PHONE] is phone_mod
