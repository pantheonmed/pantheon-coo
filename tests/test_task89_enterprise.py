"""Task 89 — GeM tool, audit logs, SAML config fields."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from config import settings
from tools import gem_portal


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-enterprise")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_gem_search_bids_list():
    out = await gem_portal.execute(
        "search_bids", {"category": "medical", "state": "Tamil Nadu"}
    )
    assert isinstance(out.get("bids"), list)


@pytest.mark.asyncio
async def test_audit_log_on_login(jwt_client: TestClient):
    await store.init()
    email = f"aud{uuid.uuid4().hex[:6]}@e.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "A", "password": "password123"},
    )
    body = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()
    uid = body["user_id"]
    events = await store.list_audit_logs(50, user_id=uid, action="login")
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_admin_audit_requires_admin(jwt_client: TestClient):
    await store.init()
    email = f"nu{uuid.uuid4().hex[:6]}@e.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "N", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.get(
        "/admin/audit-logs",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


def test_audit_migration_exists():
    p = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0020_audit_gem.sql"
    t = p.read_text(encoding="utf-8")
    assert "audit_logs" in t


def test_saml_config_fields_exist():
    assert hasattr(settings, "saml_enabled")
    assert hasattr(settings, "saml_idp_metadata_url")
    assert hasattr(settings, "saml_sp_entity_id")
