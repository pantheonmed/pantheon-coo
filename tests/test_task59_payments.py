"""Task 59 — global currency, GLOBAL_PRICING, Stripe + Razorpay billing."""
from pathlib import Path

from billing import stripe_webhook
from config import GLOBAL_PRICING, settings


def test_global_pricing_currencies():
    keys = set(GLOBAL_PRICING.keys())
    assert {"USD", "EUR", "AED", "GBP", "INR"}.issubset(keys)


def test_billing_plans_usd(client):
    r = client.get("/billing/plans?currency=USD")
    assert r.status_code == 200
    j = r.json()
    assert j.get("currency") == "USD"
    starter = next(p for p in j["plans"] if p["id"] == "starter")
    assert "$" in starter["price"] or "39" in starter["price"]


def test_stripe_in_requirements():
    req = Path(__file__).resolve().parent.parent / "requirements.txt"
    text = req.read_text()
    assert "stripe" in text.lower()


def test_stripe_webhook_handler_exists():
    assert callable(stripe_webhook)


def test_inr_razorpay_gateway_when_configured(monkeypatch, client):
    import uuid

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_x")
    monkeypatch.setattr(settings, "razorpay_key_secret", "secret")
    monkeypatch.setattr(settings, "stripe_secret_key", "")

    class _FakeOrder:
        def create(self, _):
            return {"id": "order_rzp_test_1"}

    class _FakeClient:
        order = type("O", (), {"create": _FakeOrder().create})()

    monkeypatch.setattr("billing.get_razorpay_client", lambda: _FakeClient())

    email = f"pay{uuid.uuid4().hex[:8]}@example.com"
    assert client.post(
        "/auth/register",
        json={
            "email": email,
            "name": "Pay",
            "password": "password123",
            "country_code": "IN",
        },
    ).status_code == 200
    tok = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]

    r = client.post(
        "/billing/create-order",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json().get("gateway") == "razorpay"
    assert "razorpay_order_id" in r.json()


def test_usd_stripe_gateway(monkeypatch, client):
    import uuid

    import billing as billing_mod

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_123")
    monkeypatch.setattr(settings, "razorpay_key_id", "")

    class _PI:
        @staticmethod
        def create(**kwargs):
            return type("O", (), {"id": "pi_test_1", "client_secret": "sec_test"})()

    monkeypatch.setattr(billing_mod, "stripe", type("Stripe", (), {"PaymentIntent": _PI})())

    email = f"usd{uuid.uuid4().hex[:8]}@example.com"
    assert client.post(
        "/auth/register",
        json={
            "email": email,
            "name": "Usd",
            "password": "password123",
            "country_code": "US",
        },
    ).status_code == 200
    tok = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]

    r = client.post(
        "/billing/create-order",
        json={"plan": "starter"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("gateway") == "stripe"
    assert "client_secret" in body
