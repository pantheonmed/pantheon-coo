"""Task 87 — Marketplace publish, approve, purchase, revenue split."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-mkt")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_publish_creates_pending(jwt_client: TestClient):
    await store.init()
    email = f"p{uuid.uuid4().hex[:6]}@m.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "P", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.post(
        "/marketplace/publish",
        json={
            "name": "My Tool",
            "description": "Does things",
            "code": "def x(): pass",
            "price_inr": 0,
            "category": "general",
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "pending_review"


@pytest.mark.asyncio
async def test_public_list_only_approved(jwt_client: TestClient):
    await store.init()
    uid = str(uuid.uuid4())
    await store.insert_user(
        uid,
        f"auth{uuid.uuid4().hex[:6]}@m.com",
        "A",
        user_auth.hash_password("x"),
        role="user",
        plan="free",
        api_key=user_auth.generate_api_key(),
    )
    tid = str(uuid.uuid4())
    async with store.get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO marketplace_tools
            (tool_id,name,description,author_user_id,price_inr,category,code,is_approved,created_at)
            VALUES (?,?,?,?,?,?,?,0,datetime('now'))""",
            (tid, "Hidden", "no", uid, 0, "g", "code"),
        )
        await db.commit()
    pub = jwt_client.get("/marketplace").json()["tools"]
    assert all(t["tool_id"] != tid for t in pub)


@pytest.mark.asyncio
async def test_admin_approve_and_purchase_split(jwt_client: TestClient):
    await store.init()
    adm_email = f"adm{uuid.uuid4().hex[:6]}@m.com"
    buy_email = f"buy{uuid.uuid4().hex[:6]}@m.com"
    jwt_client.post(
        "/auth/register",
        json={"email": adm_email, "name": "A", "password": "password123"},
    )
    jwt_client.post(
        "/auth/register",
        json={"email": buy_email, "name": "B", "password": "password123"},
    )
    # promote first user to admin via DB
    async with store.get_pool().acquire() as db:
        await db.execute(
            "UPDATE users SET role='admin' WHERE lower(email)=lower(?)",
            (adm_email,),
        )
        await db.commit()
    adm_tok = jwt_client.post(
        "/auth/login",
        json={"email": adm_email, "password": "password123"},
    ).json()["token"]
    buy_tok = jwt_client.post(
        "/auth/login",
        json={"email": buy_email, "password": "password123"},
    ).json()["token"]
    buy_uid = jwt_client.post(
        "/auth/login",
        json={"email": buy_email, "password": "password123"},
    ).json()["user_id"]
    tool_id = str(uuid.uuid4())
    author = str(uuid.uuid4())
    await store.insert_user(
        author,
        f"au{uuid.uuid4().hex[:6]}@m.com",
        "Au",
        user_auth.hash_password("x"),
        plan="free",
        api_key=user_auth.generate_api_key(),
    )
    async with store.get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO marketplace_tools
            (tool_id,name,description,author_user_id,price_inr,category,code,is_approved,created_at)
            VALUES (?,?,?,?,?,?,?,0,datetime('now'))""",
            (tool_id, "Paid", "tool", author, 10000, "g", "code"),
        )
        await db.commit()
    jwt_client.patch(
        f"/admin/marketplace/{tool_id}/approve",
        headers={"Authorization": f"Bearer {adm_tok}"},
    )
    jwt_client.post(
        f"/marketplace/{tool_id}/purchase",
        headers={"Authorization": f"Bearer {buy_tok}"},
    )
    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT author_share, platform_share, amount FROM tool_purchases WHERE tool_id=? AND buyer_id=?",
            (tool_id, buy_uid),
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    amount = int(row[2])
    assert int(row[0]) + int(row[1]) == amount
    assert int(row[0]) == int(amount * 0.7)
