"""
tests/test_billing.py — Razorpay billing routes (plans, auth gates, signature rejection).
"""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_billing_plans_returns_200(client: TestClient):
    r = client.get("/billing/plans")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data
    assert len(data["plans"]) >= 3
    ids = {p["id"] for p in data["plans"]}
    assert "free" in ids and "starter" in ids and "pro" in ids


def test_create_order_requires_authenticated_user(client: TestClient):
    """AUTH_MODE=none yields no user_id — expect 401."""
    r = client.post("/billing/create-order", json={"plan": "starter"})
    assert r.status_code == 401


def test_create_order_pro_monthly_with_bearer_succeeds_when_razorpay_configured(
    client: TestClient, monkeypatch
):
    """Plan tab \"Upgrade to PRO\" uses pro_monthly + Authorization: Bearer <jwt>."""
    import billing as billing_mod
    from config import settings

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_pro_m")
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret_pm")
    monkeypatch.setattr(settings, "stripe_secret_key", "")

    class _FakeOrder:
        def create(self, _):
            return {"id": "order_rzp_pro_monthly_1"}

    class _FakeClient:
        order = type("O", (), {"create": _FakeOrder().create})()

    monkeypatch.setattr(billing_mod, "get_razorpay_client", lambda: _FakeClient())

    email = f"pm{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/auth/register",
            json={
                "email": email,
                "name": "PM",
                "password": "password123",
                "country_code": "IN",
            },
        ).status_code
        == 200
    )
    tok = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]

    r = client.post(
        "/billing/create-order",
        json={"plan": "pro_monthly"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("gateway") == "razorpay"
    assert body.get("plan") == "pro_monthly"
    assert "razorpay_order_id" in body
    assert body.get("razorpay_key_id") or body.get("key_id")


def test_dashboard_billing_uses_bearer_from_stored_token():
    html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "getAuthToken" in html
    assert "access_token" in html
    assert "Bearer ' + tok" in html
    assert "showBillingAuthRequired" in html


def test_verify_payment_invalid_signature(client: TestClient, monkeypatch):
    import billing as billing_mod

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-billing-tests")
    monkeypatch.setattr(billing_mod.settings, "razorpay_key_id", "rzp_test_billing")
    monkeypatch.setattr(billing_mod.settings, "razorpay_key_secret", "test_secret_key_billing")

    email = f"bill{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/auth/register",
        json={"email": email, "name": "B", "password": "password123"},
    )
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    r = client.post(
        "/billing/verify-payment",
        json={
            "razorpay_order_id": "order_fake_123",
            "razorpay_payment_id": "pay_fake_456",
            "razorpay_signature": "not_a_valid_signature",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
