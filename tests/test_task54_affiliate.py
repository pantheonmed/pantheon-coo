"""Task 54 — Affiliate program."""
import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from security import user_auth


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-not-for-production")
    from main import app

    with TestClient(app) as c:
        yield c


def test_post_affiliate_join_creates_affiliate(jwt_client: TestClient):
    email = f"aff{uuid.uuid4().hex[:6]}@t.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "A", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_client.post("/affiliate/join", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["referral_code"]) == 8
    assert "affiliate_id" in data


@pytest.mark.asyncio
async def test_referral_code_unique_per_user():
    uid = str(uuid.uuid4())
    ph = user_auth.hash_password("password123")
    await store.insert_user(
        uid,
        f"u2{uuid.uuid4().hex[:6]}@t.com",
        "B",
        ph,
        role="user",
        plan="free",
        api_key="k" + uuid.uuid4().hex,
        industry="other",
    )
    a1 = await store.create_affiliate_for_user(uid)
    a2 = await store.get_affiliate_by_user(uid)
    assert a1["referral_code"] == a2["referral_code"]


def test_affiliate_dashboard_fields(jwt_client: TestClient):
    email = f"d{uuid.uuid4().hex[:6]}@t.com"
    jwt_client.post(
        "/auth/register",
        json={"email": email, "name": "D", "password": "password123"},
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    jwt_client.post("/affiliate/join", headers={"Authorization": f"Bearer {tok}"})
    r = jwt_client.get("/affiliate/dashboard", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    j = r.json()
    for k in (
        "referral_code",
        "referral_url",
        "total_referred",
        "total_converted",
        "total_earned_inr",
        "pending_payout",
        "recent_referrals",
    ):
        assert k in j


@pytest.mark.asyncio
async def test_commission_on_payment_and_referral_converted():
    ph = user_auth.hash_password("password123")
    aff_uid = str(uuid.uuid4())
    ref_uid = str(uuid.uuid4())
    await store.insert_user(
        aff_uid,
        f"af{uuid.uuid4().hex[:6]}@t.com",
        "AF",
        ph,
        role="user",
        plan="free",
        api_key="k" + uuid.uuid4().hex,
        industry="other",
    )
    aff = await store.create_affiliate_for_user(aff_uid, commission_pct=20.0)
    await store.insert_user(
        ref_uid,
        f"rf{uuid.uuid4().hex[:6]}@t.com",
        "RF",
        ph,
        role="user",
        plan="free",
        api_key="k" + uuid.uuid4().hex,
        industry="other",
    )
    await store.attach_referral_from_code(aff["referral_code"], ref_uid, "rf@t.com")
    await store.apply_affiliate_commission_on_payment(ref_uid, 10000)
    async with store.get_pool().acquire() as db:
        async with db.execute(
            "SELECT status, commission_inr FROM referrals WHERE referred_user_id=?",
            (ref_uid,),
        ) as cur:
            row = await cur.fetchone()
    assert row[0] == "converted"
    assert abs(float(row[1]) - 20.0) < 0.01


def test_admin_affiliates_requires_admin(client: TestClient):
    r = client.get("/admin/affiliates")
    assert r.status_code in (401, 403)


def test_affiliate_link_redirects(client: TestClient):
    r = client.get("/affiliate/link?code=ABCDEFGH", follow_redirects=False)
    assert r.status_code in (302, 307)
