"""Task 90 — Task queue, /ready, k8s manifests, worker config."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from taskqueue.task_queue import TaskQueue, get_task_queue


@pytest.mark.asyncio
async def test_enqueue_returns_int_position():
    q = TaskQueue()
    p1 = await q.enqueue("t1", "cmd", user_id="u")
    p2 = await q.enqueue("t2", "cmd", user_id="u")
    assert isinstance(p1, int) and isinstance(p2, int)


@pytest.mark.asyncio
async def test_queue_depth_int():
    d = await get_task_queue().queue_depth()
    assert isinstance(d, int)


def test_ready_ok(client: TestClient):
    r = client.get("/ready")
    assert r.status_code == 200


def test_k8s_deployment_yaml():
    p = Path(__file__).resolve().parents[1] / "k8s" / "deployment.yaml"
    raw = p.read_text(encoding="utf-8")
    assert "kind: Deployment" in raw
    assert "/ready" in raw
    try:
        import yaml  # type: ignore

        yaml.safe_load(raw)
    except ImportError:
        pass


def test_worker_count_config():
    assert hasattr(settings, "worker_count")
    assert int(settings.worker_count) >= 1
