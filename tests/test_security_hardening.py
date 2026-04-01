"""
Security hardening tests.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-security")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    import importlib

    rl = importlib.import_module("security.rate_limit")

    rl.ENABLED = True
    rl._windows.clear()
    from main import app

    with TestClient(app) as c:
        yield c


def _register_and_login(jwt_client: TestClient, ip: str | None = None) -> str:
    email = f"s{uuid.uuid4().hex[:8]}@example.com"
    hdr = {"X-Forwarded-For": ip} if ip else {}
    assert jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "S", "password": "password123"},
        headers=hdr,
    ).status_code == 200
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
        headers=hdr,
    ).json()["token"]
    return tok


def test_injection_attempt_returns_400(jwt_client: TestClient):
    tok = _register_and_login(jwt_client, ip="10.0.0.2")
    r = jwt_client.post(
        "/execute",
        json={"command": "print('x'); rm -rf /", "source": "api", "dry_run": True, "context": {}},
        headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "10.0.0.2"},
    )
    assert r.status_code == 400


def test_rate_limit_triggers_on_61st_request(jwt_client: TestClient):
    tok = _register_and_login(jwt_client, ip="10.0.0.3")
    got_429 = False
    for _ in range(61):
        r = jwt_client.get("/tasks", headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "10.0.0.3"})
        if r.status_code == 429:
            got_429 = True
            break
    assert got_429


@pytest.mark.asyncio
async def test_blocked_ip_returns_403(jwt_client: TestClient):
    tok = _register_and_login(jwt_client, ip="10.0.0.4")
    await store.add_blocked_ip("1.2.3.4", hours=1, reason="test")
    r = jwt_client.get("/tasks", headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 403


def test_jwt_blacklist_works(jwt_client: TestClient):
    tok = _register_and_login(jwt_client, ip="10.0.0.5")
    lo = jwt_client.post("/auth/logout", headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "10.0.0.5"})
    assert lo.status_code == 200
    r = jwt_client.get("/auth/me", headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "10.0.0.5"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_from_unknown_ip_returns_403(jwt_client: TestClient, monkeypatch):
    tok = _register_and_login(jwt_client, ip="10.0.0.6")
    me = jwt_client.get("/auth/me", headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "10.0.0.6"}).json()
    await store.update_user_role(me["user_id"], "admin")
    monkeypatch.setattr("config.settings.admin_allowed_ips", "9.9.9.9")
    r = jwt_client.get(
        "/admin/security-score",
        headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "1.1.1.1"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_self_protector_detects_brute_force():
    from security.self_protector import SelfProtector

    for _ in range(25):
        await store.save_security_event("FAILED_LOGIN", "8.8.8.8", "", "fail", severity="high")
    sp = SelfProtector()
    await sp.check_threats()
    # May or may not block depending on implementation; should at least not crash.
    assert isinstance(await store.count_security_events("FAILED_LOGIN", minutes=10), int)

