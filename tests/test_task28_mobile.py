"""
Task 28 — PWA manifest, /app route, mobile-friendly dashboard assets.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_get_static_manifest_returns_200(client: TestClient):
    r = client.get("/static/manifest.json")
    assert r.status_code == 200


def test_manifest_json_has_required_fields(client: TestClient):
    r = client.get("/static/manifest.json")
    data = r.json()
    assert data.get("name")
    assert data.get("start_url")
    assert isinstance(data.get("icons"), list)
    assert len(data["icons"]) >= 1


def test_get_app_returns_200(client: TestClient):
    r = client.get("/app")
    assert r.status_code == 200


def test_dashboard_html_has_media_query_and_viewport():
    root = Path(__file__).resolve().parent.parent
    html = (root / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "@media (max-width: 768px)" in html
    assert 'name="viewport"' in html
    assert "width=device-width" in html
