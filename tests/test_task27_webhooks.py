"""
Task 27 — outbound webhooks (subscriptions, HMAC delivery, failure handling).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-task27")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _register_and_token(jwt_client: TestClient) -> tuple[str, str]:
    email = f"w{uuid.uuid4().hex[:10]}@t.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "W", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    uid = jwt_client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["user_id"]
    return uid, tok


def test_post_webhooks_creates_subscription_returns_secret(jwt_client: TestClient):
    _, tok = _register_and_token(jwt_client)
    r = jwt_client.post(
        "/webhooks",
        json={"url": "https://example.com/webhook/here"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "webhook_id" in data
    assert "secret" in data
    assert len(data["secret"]) == 64


def test_get_webhooks_does_not_return_full_secret(jwt_client: TestClient):
    _, tok = _register_and_token(jwt_client)
    jwt_client.post(
        "/webhooks",
        json={"url": "https://example.com/webhook/here"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = jwt_client.get("/webhooks", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    for w in r.json().get("webhooks", []):
        assert "secret" not in w or w.get("secret") is None
        assert "secret_tail" in w


@pytest.mark.asyncio
async def test_fire_webhook_sends_correct_hmac_signature():
    await store.init()
    uid = str(uuid.uuid4())
    wid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"u{uuid.uuid4().hex[:8]}@t.com",
        "U",
        user_auth.hash_password("password123"),
        api_key=user_auth.generate_api_key(),
    )
    await store.insert_webhook_subscription(
        wid,
        uid,
        "https://example.com/hook",
        json.dumps(["task.completed", "task.failed"]),
        "a" * 64,
    )
    captured: dict = {}

    async def fake_post(url, content=None, headers=None, **kw):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        r = MagicMock()
        r.status_code = 200
        return r

    mock_inst = MagicMock()
    mock_inst.post = AsyncMock(side_effect=fake_post)
    mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
    mock_inst.__aexit__ = AsyncMock(return_value=None)

    with patch("webhook_sender.httpx.AsyncClient", return_value=mock_inst):
        from webhook_sender import fire_webhook

        await fire_webhook(uid, "task.completed", {"task_id": "abc", "goal": "g"})
        await asyncio.sleep(0.25)

    assert captured.get("url") == "https://example.com/hook"
    h = captured.get("headers") or {}
    assert h.get("X-Pantheon-Signature", "").startswith("sha256=")
    body = captured.get("content")
    if isinstance(body, bytes):
        body = body.decode()
    assert "task.completed" in body


@pytest.mark.asyncio
async def test_failure_count_increments_on_500_and_retry_skips_slow_sleep():
    await store.init()
    monkeypatch_sleep = AsyncMock(return_value=None)
    uid = str(uuid.uuid4())
    wid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"u{uuid.uuid4().hex[:8]}@t.com",
        "U",
        user_auth.hash_password("password123"),
        api_key=user_auth.generate_api_key(),
    )
    await store.insert_webhook_subscription(
        wid,
        uid,
        "https://example.com/hook",
        json.dumps(["task.completed"]),
        "b" * 64,
    )

    n = {"i": 0}

    async def fake_post(url, content=None, headers=None, **kw):
        n["i"] += 1
        r = MagicMock()
        r.status_code = 500 if n["i"] == 1 else 200
        return r

    mock_inst = MagicMock()
    mock_inst.post = AsyncMock(side_effect=fake_post)
    mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
    mock_inst.__aexit__ = AsyncMock(return_value=None)

    with patch("webhook_sender.httpx.AsyncClient", return_value=mock_inst):
        with patch("webhook_sender.asyncio.sleep", monkeypatch_sleep):
            from webhook_sender import _deliver_one

            sub = {
                "webhook_id": wid,
                "url": "https://example.com/hook",
                "secret": "b" * 64,
            }
            await _deliver_one(sub, "task.completed", {"task_id": "x"})

    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT failure_count FROM webhook_subscriptions WHERE webhook_id=?",
            (wid,),
        ) as cur:
            fc = (await cur.fetchone())[0]
    assert int(fc) >= 1


@pytest.mark.asyncio
async def test_five_failures_deactivate_webhook():
    await store.init()
    wid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"u{uuid.uuid4().hex[:8]}@t.com",
        "U",
        user_auth.hash_password("password123"),
        api_key=user_auth.generate_api_key(),
    )
    await store.insert_webhook_subscription(
        wid,
        uid,
        "https://example.com/h",
        json.dumps(["task.completed"]),
        "c" * 64,
    )
    for _ in range(5):
        await store.increment_webhook_failure(wid)
    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT is_active FROM webhook_subscriptions WHERE webhook_id=?",
            (wid,),
        ) as cur:
            row = await cur.fetchone()
    assert int(row[0]) == 0


def test_delete_webhook_deactivates(jwt_client: TestClient):
    _, tok = _register_and_token(jwt_client)
    cr = jwt_client.post(
        "/webhooks",
        json={"url": "https://example.com/webhook/del"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    wid = cr.json()["webhook_id"]
    r = jwt_client.delete(
        f"/webhooks/{wid}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    lst = jwt_client.get("/webhooks", headers={"Authorization": f"Bearer {tok}"}).json().get("webhooks", [])
    match = next((x for x in lst if x["webhook_id"] == wid), None)
    assert match is not None
    assert int(match.get("is_active", 0)) == 0
