"""Task 79 — admin dashboard snapshot API + dashboard markers."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from config import PLAN_PRICING
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-task79")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_admin_dashboard_stats_requires_privileged_user(jwt_client: TestClient):
    await store.init()
    email = f"u{uuid.uuid4().hex[:8]}@t79.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "U", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.get(
        "/admin/dashboard-stats",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard_stats_returns_sections(jwt_client: TestClient):
    await store.init()
    email = f"adm{uuid.uuid4().hex[:8]}@t79.com"
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
    r = jwt_client.get(
        "/admin/dashboard-stats",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    d = r.json()
    assert "system" in d
    assert "uptime_seconds" in d["system"]
    assert "users" in d
    assert "revenue" in d
    assert "usage" in d


@pytest.mark.asyncio
async def test_mrr_matches_plan_breakdown_from_store():
    """MRR in stats must match sum of PLAN_PRICING × plan counts (store formula)."""
    await store.init()
    stats = await store.get_admin_dashboard_stats()
    pb = stats["users"]["plan_breakdown"]
    expected_paise = 0
    for plan_name, cnt in pb.items():
        p = PLAN_PRICING.get(plan_name)
        if p:
            expected_paise += int(p["amount"]) * int(cnt)
    assert abs(float(stats["revenue"]["mrr_inr"]) - round(expected_paise / 100.0, 2)) < 0.02


def test_admin_tab_hidden_in_dashboard_html():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert 'id="admin-tab-btn"' in html
    assert "display:none" in html
