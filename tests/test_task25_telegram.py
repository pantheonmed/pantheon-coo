"""
Task 25 — Telegram webhook, notifications, orchestrator notify.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from security.auth import PUBLIC_PATHS


def test_webhook_telegram_in_public_paths():
    assert "/webhook/telegram" in PUBLIC_PATHS


@pytest.mark.asyncio
async def test_send_telegram_uses_httpx(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")

    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_c = AsyncMock()
    mock_c.post = AsyncMock(return_value=mock_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_c)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("notifications.httpx.AsyncClient", return_value=mock_cm):
        from notifications import send_telegram

        ok = await send_telegram("12345", "hello")
        assert ok is True
        assert mock_c.post.called


def test_setup_requires_token(client: TestClient):
    r = client.get("/webhook/telegram/setup", params={"url": "https://example.com/hook"})
    assert r.status_code == 503


@patch("telegram_bot.httpx.AsyncClient")
def test_start_returns_welcome(mock_client_cls, client: TestClient, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_c = AsyncMock()
    mock_c.post = AsyncMock(return_value=mock_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_c)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = mock_cm

    r = client.post(
        "/webhook/telegram",
        json={
            "update_id": 1,
            "message": {
                "chat": {"id": 999},
                "text": "/start",
            },
        },
    )
    assert r.status_code == 200
    assert mock_c.post.called
    body = mock_c.post.call_args[1]["json"]["text"]
    assert "Welcome to Pantheon COO" in body


@patch("telegram_bot._handle_user_text", new_callable=AsyncMock)
def test_text_dispatches_handler(mock_handle, client: TestClient, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "tok")

    r = client.post(
        "/webhook/telegram",
        json={
            "update_id": 2,
            "message": {
                "chat": {"id": 42},
                "text": "echo hello from telegram",
            },
        },
    )
    assert r.status_code == 200
    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][0] == "42"


@pytest.mark.asyncio
async def test_notify_telegram_on_done(monkeypatch):
    import memory.store as store
    import orchestrator
    from models import TaskStatus

    tid = "test-tg-notify-001"
    await store.create_task(tid, "x", "telegram", telegram_chat_id="99")
    await store.update_status(
        tid,
        TaskStatus.DONE,
        summary="done",
        eval_score=0.9,
        iterations=1,
    )

    sent = []

    async def fake_send(cid: str, text: str) -> bool:
        sent.append((cid, text))
        return True

    monkeypatch.setattr("notifications.send_telegram", fake_send)

    await orchestrator._notify_telegram_if_needed(
        tid,
        {"telegram_chat_id": "99"},
    )
    assert sent and sent[0][0] == "99"
    assert "✅" in sent[0][1]


@pytest.mark.asyncio
async def test_status_lists_tasks(monkeypatch):
    import memory.store as store
    import uuid
    from config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "tok")

    from models import TaskStatus

    cid = "777"
    t1 = str(uuid.uuid4())
    t2 = str(uuid.uuid4())
    await store.create_task(t1, "a", "telegram", telegram_chat_id=cid)
    await store.create_task(t2, "b", "telegram", telegram_chat_id=cid)
    await store.update_status(t2, TaskStatus.DONE, summary="ok", eval_score=1.0, iterations=1)

    mock_post = AsyncMock(return_value=MagicMock(is_success=True))
    mock_c = AsyncMock()
    mock_c.post = mock_post
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_c)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("telegram_bot.httpx.AsyncClient", return_value=mock_cm):
        from telegram_bot import _send_status

        await _send_status(cid)

    txt = mock_post.call_args[1]["json"]["text"]
    assert "Last tasks" in txt or "done" in txt.lower()
