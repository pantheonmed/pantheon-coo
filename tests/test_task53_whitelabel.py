"""Task 53 — White-label branding endpoints & dashboard."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_get_config_branding_200_and_name(client: TestClient):
    r = client.get("/config/branding")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data
    assert "powered_by" in data
    assert data["powered_by"] == "Pantheon COO OS"


def test_dashboard_html_has_load_branding():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "dashboard.html").read_text()
    assert "loadBranding" in html


def test_white_label_name_in_branding_response(client: TestClient):
    from config import settings

    n = settings.white_label_name
    r = client.get("/config/branding")
    assert r.json().get("name") == n


def test_patch_admin_branding_requires_admin(client: TestClient):
    r = client.patch("/admin/branding", json={"name": "X"})
    assert r.status_code in (401, 403)


def test_get_admin_branding_requires_admin(client: TestClient):
    r = client.get("/admin/branding")
    assert r.status_code in (401, 403)


def test_public_branding_has_primary_color(client: TestClient):
    r = client.get("/config/branding")
    assert "primary_color" in r.json()
