"""Task 88 — Insights engine + HTTP routes."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from insights_engine import get_insights_engine
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-insights")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_generate_weekly_insights_fields():
    await store.init()
    uid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"i{uuid.uuid4().hex[:6]}@x.com",
        "I",
        user_auth.hash_password("x"),
        plan="free",
        api_key=user_auth.generate_api_key(),
    )
    d = await get_insights_engine().generate_weekly_insights(uid)
    assert "success_rate" in d
    assert "recommendations" in d


@pytest.mark.asyncio
async def test_predict_task_success_has_rate():
    p = await get_insights_engine().predict_task_success("check disk", "devops")
    assert "success_rate" in p


@pytest.mark.asyncio
async def test_automation_opportunities_list():
    await store.init()
    uid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"j{uuid.uuid4().hex[:6]}@x.com",
        "J",
        user_auth.hash_password("x"),
        plan="free",
        api_key=user_auth.generate_api_key(),
    )
    for _ in range(3):
        tid = str(uuid.uuid4())
        await store.create_task(tid, "same command repeat", "t", user_id=uid)
    ops = await get_insights_engine().find_automation_opportunities(uid)
    assert isinstance(ops, list)


@pytest.mark.asyncio
async def test_weekly_report_http(jwt_client: TestClient):
    await store.init()
    email = f"u{uuid.uuid4().hex[:6]}@x.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "U", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.post(
        "/insights/weekly-report",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert "tasks_completed" in r.json()


@pytest.mark.asyncio
async def test_automation_http(jwt_client: TestClient):
    await store.init()
    email = f"v{uuid.uuid4().hex[:6]}@x.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "V", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.get(
        "/insights/automation-opportunities",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert "opportunities" in r.json()
