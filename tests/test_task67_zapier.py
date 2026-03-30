"""Task 67 — Zapier tool + inbound webhook."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from models import ToolName
from tools import REGISTRY
from tools import zapier as zapier_tool


def test_toolname_zapier_in_enum():
    assert ToolName.ZAPIER.value == "zapier"
    assert ToolName.ZAPIER in REGISTRY


@pytest.mark.asyncio
async def test_send_to_webhook_posts():
    from unittest.mock import MagicMock

    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.status_code = 200
    fake_resp.text = "ok"
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=fake_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.zapier.httpx.AsyncClient", return_value=mock_cm):
        out = await zapier_tool.execute(
            "send_to_webhook",
            {"webhook_url": "https://hooks.zapier.com/hooks/catch/123/abc/", "data": {"a": 1}, "method": "POST"},
        )
    assert out["success"] is True
    assert out["response_code"] == 200


@pytest.mark.asyncio
async def test_send_to_webhook_blocks_localhost():
    from security.sandbox import SecurityError

    with pytest.raises(SecurityError):
        await zapier_tool.execute(
            "send_to_webhook",
            {"webhook_url": "http://localhost:8000/hook", "data": {}},
        )


def test_webhook_zapier_creates_task(monkeypatch):
    monkeypatch.setattr(settings, "zapier_webhook_secret", "super-secret-zap")
    from main import app

    with TestClient(app) as c:
        r = c.post(
            "/webhook/zapier",
            headers={"X-Zapier-Secret": "super-secret-zap"},
            json={"command": "test zapier webhook command here", "user_email": "", "data": {}},
        )
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert data.get("status") == "queued"
    assert "status_url" in data


def test_webhook_zapier_rejects_bad_secret(monkeypatch):
    monkeypatch.setattr(settings, "zapier_webhook_secret", "good")
    from main import app

    with TestClient(app) as c:
        r = c.post(
            "/webhook/zapier",
            headers={"X-Zapier-Secret": "bad"},
            json={"command": "x" * 10, "user_email": ""},
        )
    assert r.status_code == 401
