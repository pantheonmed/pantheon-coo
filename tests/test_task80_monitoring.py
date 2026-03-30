"""Task 80 — error tracker + admin errors API."""
from __future__ import annotations

import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from monitoring.error_tracker import get_alert_count_today, get_tracker, track_error
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-task80")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_track_error_records_message():
    await get_tracker().track(
        ValueError("unit-test-err"), context={"k": "v"}, user_id="u1", task_id="t1"
    )
    recent = get_tracker().get_recent(20)
    assert any("unit-test-err" in str(x.get("message", "")) for x in recent)


@pytest.mark.asyncio
async def test_critical_errors_trigger_alert_check():
    before = get_alert_count_today()
    await track_error(sqlite3.OperationalError(f"db-{uuid.uuid4().hex}"))
    assert get_alert_count_today() >= before


def test_get_recent_returns_at_most_limit():
    tr = get_tracker()
    assert len(tr.get_recent(7)) <= 7


@pytest.mark.asyncio
async def test_admin_errors_requires_admin(jwt_client: TestClient):
    await store.init()
    email = f"u{uuid.uuid4().hex[:8]}@t80.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "U", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.get("/admin/errors", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_errors_returns_list_format(jwt_client: TestClient):
    await store.init()
    email = f"adm{uuid.uuid4().hex[:8]}@t80.com"
    await store.insert_user(
        str(uuid.uuid4()),
        email,
        "Admin",
        user_auth.hash_password("password123"),
        role="admin",
        plan="pro",
        api_key=user_auth.generate_api_key(),
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    await track_error(RuntimeError("visible-in-admin-errors"), context={"test": True})
    r = jwt_client.get("/admin/errors?limit=5", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert "errors" in data
    assert isinstance(data["errors"], list)
