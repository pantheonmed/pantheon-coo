"""
Task 26 — analytics events, admin API, CSV export.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from analytics import track
from security import user_auth
from tests.test_e2e import (
    CONFIDENCE_HIGH,
    EVALUATOR_PASS,
    MEMORY_OUT,
    REASONING,
    WRITE_FILE_PLAN,
    _mock_claude,
)


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-task26")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_track_stores_event_in_db():
    await store.init()
    uid = "u-" + uuid.uuid4().hex[:10]
    await track("task_submitted", uid, goal_type="build", foo=1)
    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT event_type, properties FROM analytics_events WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "task_submitted"
    props = json.loads(row[1] or "{}")
    assert props.get("goal_type") == "build"


def test_get_admin_analytics_forbidden_for_regular_user(jwt_client: TestClient):
    email = f"{uuid.uuid4().hex[:10]}@t.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "U", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.get("/admin/analytics", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_admin_analytics_admin_200(jwt_client: TestClient):
    email = f"adm{uuid.uuid4().hex[:8]}@example.com"
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
        "/admin/analytics?period=7d",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["period"] == "7d"
    assert "new_users" in d
    assert "active_users" in d
    assert "total_tasks" in d
    assert "success_rate" in d
    assert "avg_score" in d
    assert "top_goal_types" in d
    assert "daily_tasks" in d
    assert "churn_risk_users" in d


@pytest.mark.asyncio
async def test_admin_analytics_export_csv_content_type(jwt_client: TestClient):
    email = f"adm{uuid.uuid4().hex[:8]}@example.com"
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
        "/admin/analytics/export?period=7d",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct


@pytest.mark.asyncio
async def test_task_completed_event_after_successful_orchestrator():
    task_id = str(uuid.uuid4())

    async with store.get_pool().acquire() as db:
        async with db.execute("SELECT COALESCE(MAX(id),0) FROM analytics_events") as cur:
            before_id = (await cur.fetchone())[0]

    with patch("anthropic.Anthropic") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.messages.create.side_effect = _mock_claude(
            {
                "Reasoning Agent": REASONING,
                "Planning Agent": WRITE_FILE_PLAN,
                "Evaluator Agent": EVALUATOR_PASS,
                "Memory Agent": MEMORY_OUT,
                "confidence evaluator": CONFIDENCE_HIGH,
            }
        )
        mock_cls.return_value = mock_instance
        await store.init()
        await store.create_task(task_id, "Write hello.txt to workspace", "test")
        import orchestrator

        await orchestrator.run(
            task_id=task_id,
            command="Write hello.txt to workspace",
            context={},
            dry_run=False,
        )

    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM analytics_events WHERE id > ? AND event_type=?",
            (before_id, "task_completed"),
        ) as cur:
            n = (await cur.fetchone())[0]
    assert n >= 1
