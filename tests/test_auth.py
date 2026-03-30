"""
tests/test_auth.py
──────────────────
Multi-user auth: register, login, password checks, task listing isolation.
Uses default TestClient (AUTH_MODE=none) where possible; JWT_SECRET is set
in conftest so /auth/login can mint tokens.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from models import ExecutionStep, ToolName, StepStatus
from security.sandbox import reset_user_workspace, set_user_workspace, validate_step
from security import user_auth


@pytest.mark.asyncio
async def test_list_tasks_filters_by_user(client: TestClient):
    """Uses async store calls; client fixture ensures DB is initialised."""
    """Store-level: regular user_id filter vs admin sees all."""
    u1 = str(uuid.uuid4())
    u2 = str(uuid.uuid4())
    t1 = str(uuid.uuid4())
    t2 = str(uuid.uuid4())
    t3 = str(uuid.uuid4())
    await store.create_task(t1, "cmd one", "api", user_id=u1)
    await store.create_task(t2, "cmd two", "api", user_id=u2)
    await store.create_task(t3, "cmd three", "api", user_id=u1)
    rows_u1 = await store.list_tasks(limit=50, user_id=u1, is_admin=False)
    ids = {r["task_id"] for r in rows_u1}
    assert ids == {t1, t3}
    all_rows = await store.list_tasks(limit=50, user_id=None, is_admin=True)
    all_ids = {r["task_id"] for r in all_rows}
    assert {t1, t2, t3}.issubset(all_ids)


class TestAuthRegisterLogin:
    def test_register_returns_api_key(self, client: TestClient):
        email = f"u{uuid.uuid4().hex[:8]}@example.com"
        resp = client.post(
            "/auth/register",
            json={"email": email, "name": "Test User", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert len(data["api_key"]) > 20
        assert data["email"] == email.lower()
        assert data["plan"] == "free"

    def test_login_correct_password_returns_jwt(self, client: TestClient):
        email = f"login{uuid.uuid4().hex[:8]}@example.com"
        r1 = client.post(
            "/auth/register",
            json={"email": email, "name": "L", "password": "password123"},
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert r2.status_code == 200
        assert "token" in r2.json()
        assert r2.json()["email"] == email.lower()

    def test_login_wrong_password_401(self, client: TestClient):
        email = f"bad{uuid.uuid4().hex[:8]}@example.com"
        client.post(
            "/auth/register",
            json={"email": email, "name": "B", "password": "password123"},
        )
        resp = client.post(
            "/auth/login",
            json={"email": email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401


def test_user_workspace_filesystem_allowed():
    ws = os.environ.get("WORKSPACE_DIR", "/tmp/pantheon_v2")
    uid = "test-user-sandbox"
    tok = set_user_workspace(uid)
    try:
        path = f"{ws}/users/{uid}/out.txt"
        step = ExecutionStep(
            step_id=1,
            tool=ToolName.FILESYSTEM,
            action="read",
            params={"path": path},
            status=StepStatus.PENDING,
        )
        validate_step(step)
    finally:
        reset_user_workspace(tok)


class TestAuthJwtModeHttp:
    """AUTH_MODE=jwt via monkeypatch — require_auth reads os.environ each request."""

    @pytest.fixture
    def jwt_client(self, monkeypatch):
        monkeypatch.setenv("AUTH_MODE", "jwt")
        monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-key-for-pytest")
        from main import app

        with TestClient(app) as c:
            yield c

    def test_me_with_valid_jwt(self, jwt_client: TestClient):
        email = f"jwt{uuid.uuid4().hex[:8]}@example.com"
        jwt_client.post(
            "/auth/register",
            json={"email": email, "name": "J", "password": "password123"},
        )
        login = jwt_client.post(
            "/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert login.status_code == 200
        token = login.json()["token"]
        me = jwt_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == email.lower()

    def test_tasks_only_current_user(self, jwt_client: TestClient):
        e1 = f"a{uuid.uuid4().hex[:8]}@example.com"
        e2 = f"b{uuid.uuid4().hex[:8]}@example.com"
        jwt_client.post(
            "/auth/register",
            json={"email": e1, "name": "A", "password": "password123"},
        )
        jwt_client.post(
            "/auth/register",
            json={"email": e2, "name": "B", "password": "password123"},
        )
        t1 = jwt_client.post(
            "/auth/login",
            json={"email": e1, "password": "password123"},
        ).json()["token"]
        t2 = jwt_client.post(
            "/auth/login",
            json={"email": e2, "password": "password123"},
        ).json()["token"]
        tid1 = jwt_client.post(
            "/execute",
            json={"command": "user one unique marker xyz"},
            headers={"Authorization": f"Bearer {t1}"},
        ).json()["task_id"]
        tid2 = jwt_client.post(
            "/execute",
            json={"command": "user two unique marker abc"},
            headers={"Authorization": f"Bearer {t2}"},
        ).json()["task_id"]
        r1 = jwt_client.get(
            "/tasks",
            headers={"Authorization": f"Bearer {t1}"},
        )
        assert r1.status_code == 200
        ids1 = {t["task_id"] for t in r1.json()["tasks"]}
        assert tid1 in ids1
        assert tid2 not in ids1

    @pytest.mark.asyncio
    async def test_admin_sees_all_tasks(self, jwt_client: TestClient):
        import memory.store as st

        admin_id = str(uuid.uuid4())
        await st.insert_user(
            admin_id,
            "admin@example.com",
            "Admin",
            user_auth.hash_password("adminpass123"),
            role="admin",
            plan="pro",
            api_key=user_auth.generate_api_key(),
        )

        email = f"usr{uuid.uuid4().hex[:8]}@example.com"
        jwt_client.post(
            "/auth/register",
            json={"email": email, "name": "U", "password": "password123"},
        )
        utok = jwt_client.post(
            "/auth/login",
            json={"email": email, "password": "password123"},
        ).json()["token"]
        reg_tid = jwt_client.post(
            "/execute",
            json={"command": "regular user task marker rutm"},
            headers={"Authorization": f"Bearer {utok}"},
        ).json()["task_id"]
        login_ad = jwt_client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "adminpass123"},
        )
        assert login_ad.status_code == 200
        atok = login_ad.json()["token"]
        lst = jwt_client.get(
            "/tasks",
            headers={"Authorization": f"Bearer {atok}"},
        )
        assert lst.status_code == 200
        admin_ids = {t["task_id"] for t in lst.json()["tasks"]}
        assert reg_tid in admin_ids
