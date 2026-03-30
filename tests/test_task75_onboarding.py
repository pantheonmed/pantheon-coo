"""Task 75 — onboarding samples, tutorials, welcome email, dashboard tour."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_onboarding_samples_medical_count(client: TestClient):
    r = client.get("/onboarding/samples?industry=medical")
    assert r.status_code == 200
    d = r.json()
    assert d.get("industry") == "medical"
    assert len(d.get("samples", [])) == 5


def test_onboarding_samples_retail_count(client: TestClient):
    r = client.get("/onboarding/samples?industry=retail")
    assert r.status_code == 200
    assert len(r.json().get("samples", [])) == 5


def test_tutorials_list(client: TestClient):
    r = client.get("/tutorials")
    assert r.status_code == 200
    items = r.json().get("tutorials", [])
    assert isinstance(items, list)
    assert len(items) >= 5


def test_welcome_email_template_exists():
    p = ROOT / "templates" / "emails" / "welcome.html"
    assert p.is_file()
    t = p.read_text(encoding="utf-8")
    assert "Welcome to Pantheon COO OS" in t
    assert "Pantheon Meditech" in t


@pytest.mark.parametrize(
    "name",
    [
        "tutorial_1_first_task.md",
        "tutorial_2_schedules.md",
        "tutorial_3_projects.md",
        "tutorial_4_templates.md",
        "tutorial_5_integrations.md",
    ],
)
def test_tutorial_markdown_exists(name: str):
    p = ROOT / "static" / "tutorials" / name
    assert p.is_file()
    assert len(p.read_text(encoding="utf-8").strip()) > 20


def test_dashboard_has_tour_overlay():
    html = (ROOT / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert "tour-overlay" in html
    assert "tour_completed" in html or "TOUR_KEY" in html
