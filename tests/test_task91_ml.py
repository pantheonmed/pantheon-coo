"""Task 91 — ML data collector + admin routes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from ml.data_collector import TrainingDataCollector
from ml.training_config import FINE_TUNE_CONFIG


@pytest.fixture
def jwt_admin(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-ml-admin")
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.mark.asyncio
async def test_collect_successful_tasks_list():
    await store.init()
    rows = await TrainingDataCollector().collect_successful_tasks(limit=5, min_score=0.0)
    assert isinstance(rows, list)


@pytest.mark.asyncio
async def test_export_jsonl_messages_format(tmp_path):
    await store.init()
    p = tmp_path / "out.jsonl"
    n = await TrainingDataCollector().export_jsonl(str(p), "planning")
    assert n >= 0
    if p.is_file() and p.stat().st_size > 0:
        line = p.read_text(encoding="utf-8").splitlines()[0]
        obj = json.loads(line)
        assert "messages" in obj


def test_fine_tune_config_keys():
    assert "base_model" in FINE_TUNE_CONFIG


@pytest.mark.asyncio
async def test_ml_stats_requires_admin(jwt_admin: TestClient):
    await store.init()
    email = f"u{__import__('uuid').uuid4().hex[:6]}@ml.com"
    jwt_admin.post(
        "/auth/register",
        json={"email": email, "name": "U", "password": "password123"},
    )
    tok = jwt_admin.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]
    r = jwt_admin.get(
        "/admin/ml/stats",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
