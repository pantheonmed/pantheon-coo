"""Task 66 — Multi-subscriber SSE + task sharing."""
import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store


@pytest.mark.asyncio
async def test_multiple_sse_subscribers_receive_same_event():
    await store.init()
    tid = "collab-sse-" + uuid.uuid4().hex[:8]
    q1 = store.subscribe_task_stream(tid)
    q2 = store.subscribe_task_stream(tid)
    await store.push_stream_event(tid, "loop_start", {"iteration": 1, "max": 3})
    import asyncio

    ev1 = await asyncio.wait_for(q1.get(), timeout=2.0)
    ev2 = await asyncio.wait_for(q2.get(), timeout=2.0)
    assert ev1["event_type"] == "loop_start"
    assert ev2["event_type"] == "loop_start"
    store.unsubscribe_task_stream(tid, q1)
    store.unsubscribe_task_stream(tid, q2)


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-key-for-pytest")
    from main import app

    with TestClient(app) as c:
        yield c


def test_post_share_returns_share_url(jwt_client: TestClient):
    import asyncio

    asyncio.get_event_loop().run_until_complete(store.init())
    email = f"share{uuid.uuid4().hex[:8]}@example.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "S", "password": "password123"},
    )
    login = jwt_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200
    token = login.json()["token"]
    uid = login.json()["user_id"]
    tid = str(uuid.uuid4())
    asyncio.get_event_loop().run_until_complete(store.create_task(tid, "shared goal", "api", user_id=uid))
    r = jwt_client.post(
        f"/tasks/{tid}/share",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200
    data = r.json()
    assert "share_url" in data
    assert "/shared/" in data["share_url"]
    assert "expires_at" in data


def test_get_shared_unauthenticated(jwt_client: TestClient):
    import asyncio

    asyncio.get_event_loop().run_until_complete(store.init())
    email = f"pub{uuid.uuid4().hex[:8]}@example.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "P", "password": "password123"},
    )
    login = jwt_client.post("/auth/login", json={"email": email, "password": "password123"})
    token = login.json()["token"]
    uid = login.json()["user_id"]
    tid = str(uuid.uuid4())
    asyncio.get_event_loop().run_until_complete(
        store.create_task(tid, "public share test", "api", user_id=uid)
    )
    sh = jwt_client.post(
        f"/tasks/{tid}/share",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert sh.status_code == 200
    tok = sh.json()["token"]
    from main import app

    with TestClient(app) as anon:
        raw = anon.get(f"/shared/{tok}")
    assert raw.status_code == 200
    body = raw.json()
    assert body["task"]["task_id"] == tid
    assert "logs" in body


@pytest.mark.asyncio
async def test_expired_share_token_404():
    await store.init()
    tid = str(uuid.uuid4())
    await store.create_task(tid, "x", "api", user_id=None)
    await store.insert_task_share("expiredtok", tid, None, "2000-01-01T00:00:00")
    from main import app

    with TestClient(app) as c:
        r = c.get("/shared/expiredtok")
    assert r.status_code == 404
