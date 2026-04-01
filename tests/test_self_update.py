"""
Self-update API smoke tests.

We mock the heavy parts (git/pytest/model) and validate:
  - /self-update returns required shape and confirmation_needed True
  - /self-update/confirm accepts haan/nahi and returns ok
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def jwt_client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-self-update")
    from main import app

    with TestClient(app) as c:
        yield c


def _register_and_login(jwt_client: TestClient) -> str:
    import uuid

    email = f"su{uuid.uuid4().hex[:8]}@example.com"
    assert (
        jwt_client.post(
            "/auth/register",
            json={"email": email, "name": "SU", "password": "password123"},
        ).status_code
        == 200
    )
    tok = jwt_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    return tok


def test_self_update_prepare_returns_shape(jwt_client: TestClient, monkeypatch):
    tok = _register_and_login(jwt_client)

    fake_out = {
        "plan": ["Analyze", "Change", "Test", "Diff"],
        "files_affected": ["main.py"],
        "estimated_time": "10 min",
        "confirmation_needed": True,
        "token": "tok_test_123",
        "diff": "diff --git a/main.py b/main.py",
    }

    monkeypatch.setattr("agents.self_update_agent.settings.github_token", "gh_test_token")
    with patch("agents.self_update_agent.SelfUpdateAgent.prepare_self_update", new=AsyncMock(return_value=fake_out)):
        r = jwt_client.post(
            "/self-update",
            json={"instruction": "fix karo pantheon coo"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        j = r.json()
        assert "plan" in j and isinstance(j["plan"], list)
        assert "files_affected" in j and isinstance(j["files_affected"], list)
        assert "estimated_time" in j
        assert j["confirmation_needed"] is True
        assert j["token"] == "tok_test_123"


def test_self_update_confirm_nahi(jwt_client: TestClient, monkeypatch):
    tok = _register_and_login(jwt_client)

    monkeypatch.setattr("agents.self_update_agent.settings.github_token", "gh_test_token")
    with patch(
        "agents.self_update_agent.SelfUpdateAgent.confirm_and_push",
        new=AsyncMock(return_value={"ok": True, "pushed": False}),
    ):
        r = jwt_client.post(
            "/self-update/confirm",
            json={"token": "tok_test_123", "decision": "nahi"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

