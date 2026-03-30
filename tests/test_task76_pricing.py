"""Task 76 — landing pricing, billing plans, dashboard upgrade UX markers."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_landing_has_free_and_pro_tiers():
    html = (ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    upper = html.upper()
    assert "FREE" in upper
    assert "PRO" in upper
    assert "POPULAR" in upper
    assert "999" in html


def test_landing_mentions_razorpay():
    html = (ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    assert "Razorpay" in html or "razorpay" in html.lower()


def test_billing_plans_three_tiers_with_features(client: TestClient):
    r = client.get("/billing/plans?currency=INR")
    assert r.status_code == 200
    plans = r.json().get("plans", [])
    assert len(plans) >= 3
    by_id = {p["id"]: p for p in plans}
    for pid in ("free", "starter", "pro"):
        assert pid in by_id
        assert len(by_id[pid].get("features", [])) >= 1


def test_usage_bar_color_logic_in_dashboard():
    html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "usageBarColor" in html
    assert "60" in html and "90" in html
    assert "amber" in html and "green" in html and "red" in html


def test_upgrade_modal_in_dashboard():
    html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "modal-upgrade-limit" in html
    assert "You've used" in html
    assert "Upgrade Now" in html
