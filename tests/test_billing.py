"""
tests/test_billing.py — Razorpay billing routes (plans, auth gates, signature rejection).
"""
import uuid

import pytest
from fastapi.testclient import TestClient


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
