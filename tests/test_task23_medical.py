"""
Task 23 — PantheonMed vertical: templates, industry, onboarding suggested commands, dashboard theme markers.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from templates import TEMPLATES, get_template_by_id


MEDICAL_IDS = {
    "inventory_check",
    "patient_report_summary",
    "supplier_email",
    "compliance_checklist",
}


def test_medical_templates_present():
    ids = {t["id"] for t in TEMPLATES}
    assert MEDICAL_IDS.issubset(ids)
    for mid in MEDICAL_IDS:
        t = get_template_by_id(mid)
        assert t is not None
        assert t.get("category") == "medical"


def test_dashboard_theme_toggle_and_localstorage_key():
    html = open("static/dashboard.html", encoding="utf-8").read()
    assert "pantheon_theme" in html
    assert "theme-medical" in html
    assert "setDashboardTheme" in html


class TestTask23Jwt:
    @pytest.fixture
    def jwt_client(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "jwt")
        monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-key-for-task23")
        from main import app

        with TestClient(app) as c:
            yield c

    def _token(self, client: TestClient, email: str, pwd: str, industry: str = "other"):
        r = client.post(
            "/auth/register",
            json={
                "email": email,
                "name": "T",
                "password": pwd,
                "industry": industry,
            },
        )
        assert r.status_code == 200, r.text
        login = client.post("/auth/login", json={"email": email, "password": pwd})
        assert login.status_code == 200
        return login.json()["token"]

    def test_register_accepts_industry(self, jwt_client: TestClient):
        email = f"ind{uuid.uuid4().hex[:8]}@example.com"
        r = jwt_client.post(
            "/auth/register",
            json={
                "email": email,
                "name": "I",
                "password": "password123",
                "industry": "tech",
            },
        )
        assert r.status_code == 200
        assert r.json().get("industry") == "tech"

    def test_register_invalid_industry_400(self, jwt_client: TestClient):
        email = f"bad{uuid.uuid4().hex[:8]}@example.com"
        r = jwt_client.post(
            "/auth/register",
            json={
                "email": email,
                "name": "X",
                "password": "password123",
                "industry": "not_a_real_industry",
            },
        )
        assert r.status_code == 400

    def test_suggested_commands_medical(self, jwt_client: TestClient):
        email = f"med{uuid.uuid4().hex[:8]}@example.com"
        token = self._token(jwt_client, email, "password123", industry="medical")
        r = jwt_client.get(
            "/onboarding/suggested-commands",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["industry"] == "medical"
        assert len(data["commands"]) == 3
        assert "inventory" in data["commands"][1].lower()

    def test_suggested_commands_default(self, jwt_client: TestClient):
        email = f"def{uuid.uuid4().hex[:8]}@example.com"
        token = self._token(jwt_client, email, "password123", industry="tech")
        r = jwt_client.get(
            "/onboarding/suggested-commands",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["industry"] == "tech"
        assert len(data["commands"]) == 3
        assert "hello world" in data["commands"][1].lower()

    def test_templates_medical_first(self, jwt_client: TestClient):
        email = f"mf{uuid.uuid4().hex[:8]}@example.com"
        token = self._token(jwt_client, email, "password123", industry="medical")
        r = jwt_client.get(
            "/templates",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        items = r.json()["templates"]
        assert len(items) >= 4
        assert items[0]["category"] == "medical"
        assert items[1]["category"] == "medical"

    def test_onboarding_requires_auth(self, jwt_client: TestClient):
        r = jwt_client.get("/onboarding/suggested-commands")
        assert r.status_code == 401
