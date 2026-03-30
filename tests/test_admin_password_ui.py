"""Password-protected /admin HTML (ADMIN_PASSWORD), not JWT admin routes."""
from unittest.mock import patch

import pytest


@pytest.fixture
def admin_ui_password():
    from config import settings

    with patch.object(settings, "admin_password", "test-admin-ui-secret"):
        yield


def test_admin_page_503_when_password_not_set(client):
    from config import settings

    with patch.object(settings, "admin_password", ""):
        r = client.get("/admin")
        assert r.status_code == 503


def test_admin_login_required_for_data(client, admin_ui_password):
    r = client.get("/admin/data")
    assert r.status_code == 401


def test_admin_login_and_data_flow(client, admin_ui_password):
    from main import ADMIN_UI_COOKIE, _admin_session_token

    bad = client.post("/admin/login", data={"password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/admin/login", data={"password": "test-admin-ui-secret"}, follow_redirects=False)
    assert ok.status_code == 303
    cookie = ok.cookies.get(ADMIN_UI_COOKIE)
    assert cookie
    assert cookie == _admin_session_token()

    r = client.get("/admin/data", cookies={ADMIN_UI_COOKIE: cookie})
    assert r.status_code == 200
    body = r.json()
    assert "users" in body
    assert "stats" in body
    assert "allowed_plans" in body
    assert isinstance(body["allowed_plans"], list)
    assert "total_tasks" in body["stats"]
