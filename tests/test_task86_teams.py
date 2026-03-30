"""Task 86 — Teams API + migration."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import memory.store as store


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-teams")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_migration_0018_exists():
    root = Path(__file__).resolve().parents[1]
    p = root / "migrations" / "versions" / "0018_teams.sql"
    assert p.is_file()
    assert "teams" in p.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_post_teams_create_and_join(jwt_client: TestClient):
    await store.init()
    e1 = f"a{uuid.uuid4().hex[:6]}@t86.com"
    e2 = f"b{uuid.uuid4().hex[:6]}@t86.com"
    jwt_client.post(
        "/auth/register",
        json={"email": e1, "name": "A", "password": "password123"},
    )
    jwt_client.post(
        "/auth/register",
        json={"email": e2, "name": "B", "password": "password123"},
    )
    t1 = jwt_client.post(
        "/auth/login", json={"email": e1, "password": "password123"}
    ).json()["token"]
    t2 = jwt_client.post(
        "/auth/login", json={"email": e2, "password": "password123"}
    ).json()["token"]
    r = jwt_client.post(
        "/teams",
        json={"name": "Sales", "plan": "starter"},
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert r.status_code == 200
    team_id = r.json()["team_id"]
    code = r.json()["invite_code"]
    r2 = jwt_client.post(
        "/teams/join",
        json={"invite_code": code},
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_team_tasks_owner_sees_all(jwt_client: TestClient):
    await store.init()
    e1 = f"o{uuid.uuid4().hex[:6]}@t86.com"
    e2 = f"m{uuid.uuid4().hex[:6]}@t86.com"
    for e in (e1, e2):
        jwt_client.post(
            "/auth/register",
            json={"email": e, "name": "U", "password": "password123"},
        )
    t1 = jwt_client.post(
        "/auth/login", json={"email": e1, "password": "password123"}
    ).json()["token"]
    t2 = jwt_client.post(
        "/auth/login", json={"email": e2, "password": "password123"}
    ).json()["token"]
    team = jwt_client.post(
        "/teams",
        json={"name": "Eng"},
        headers={"Authorization": f"Bearer {t1}"},
    ).json()
    uid1 = jwt_client.post(
        "/auth/login", json={"email": e1, "password": "password123"}
    ).json()["user_id"]
    uid2 = jwt_client.post(
        "/auth/login", json={"email": e2, "password": "password123"}
    ).json()["user_id"]
    jwt_client.post(
        "/teams/join",
        json={"invite_code": team["invite_code"]},
        headers={"Authorization": f"Bearer {t2}"},
    )
    tid = str(uuid.uuid4())
    await store.create_task(tid, "hello team", "test", user_id=uid2)
    await store.link_team_task(team["team_id"], tid)
    r_owner = jwt_client.get(
        f"/teams/{team['team_id']}/tasks",
        headers={"Authorization": f"Bearer {t1}"},
    )
    r_mem = jwt_client.get(
        f"/teams/{team['team_id']}/tasks",
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert r_owner.status_code == 200
    assert r_mem.status_code == 200
    assert len(r_owner.json()["tasks"]) >= 1
    assert len(r_mem.json()["tasks"]) >= 1


@pytest.mark.asyncio
async def test_member_cannot_see_other_team_tasks(jwt_client: TestClient):
    await store.init()
    # user C not in team
    ec = f"c{uuid.uuid4().hex[:6]}@t86.com"
    jwt_client.post(
        "/auth/register",
        json={"email": ec, "name": "C", "password": "password123"},
    )
    tc = jwt_client.post(
        "/auth/login", json={"email": ec, "password": "password123"}
    ).json()["token"]
    # create isolated team elsewhere
    ea = f"xa{uuid.uuid4().hex[:5]}@t86.com"
    jwt_client.post(
        "/auth/register",
        json={"email": ea, "name": "X", "password": "password123"},
    )
    ta = jwt_client.post(
        "/auth/login", json={"email": ea, "password": "password123"}
    ).json()["token"]
    team = jwt_client.post(
        "/teams",
        json={"name": "Private"},
        headers={"Authorization": f"Bearer {ta}"},
    ).json()
    r = jwt_client.get(
        f"/teams/{team['team_id']}/tasks",
        headers={"Authorization": f"Bearer {tc}"},
    )
    assert r.status_code == 403
