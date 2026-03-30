"""
tests/test_api.py
──────────────────
Integration tests for the Pantheon COO OS API.

Tests the full HTTP surface: endpoint existence, response shapes,
error handling, and basic happy-path flows.

Claude API is mocked via conftest.py — no real API calls.
"""
import json
import sqlite3
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Health + Stats
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthEndpoints:
    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self, client: TestClient):
        data = client.get("/health").json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "app" in data
        assert "version" in data
        assert "agents" in data

    def test_health_includes_ports(self, client: TestClient):
        data = client.get("/health").json()
        assert "ports" in data
        assert "backend" in data["ports"]

    def test_stats_returns_200(self, client: TestClient):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_stats_has_task_counts(self, client: TestClient):
        data = client.get("/stats").json()
        assert "total" in data


# ─────────────────────────────────────────────────────────────────────────────
# Task execution
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteEndpoint:
    def test_execute_returns_202(self, client: TestClient):
        resp = client.post("/execute", json={"command": "create a test file"})
        assert resp.status_code == 202

    def test_execute_returns_task_id(self, client: TestClient):
        data = client.post("/execute", json={"command": "do something"}).json()
        assert "task_id" in data
        assert len(data["task_id"]) == 36  # UUID format

    def test_execute_dry_run_returns_queued(self, client: TestClient):
        data = client.post("/execute", json={
            "command": "list workspace contents",
            "dry_run": True,
        }).json()
        assert "task_id" in data
        assert data["status"] in ("queued", "done")

    def test_execute_empty_command_rejected(self, client: TestClient):
        resp = client.post("/execute", json={"command": ""})
        assert resp.status_code == 422  # pydantic validation

    def test_execute_short_command_rejected(self, client: TestClient):
        resp = client.post("/execute", json={"command": "hi"})
        assert resp.status_code == 422

    def test_execute_source_field_accepted(self, client: TestClient):
        data = client.post("/execute", json={
            "command": "check disk space",
            "source": "whatsapp",
        }).json()
        assert "task_id" in data


# ─────────────────────────────────────────────────────────────────────────────
# Task status polling
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskEndpoints:
    def test_get_queued_task(self, client: TestClient):
        task_id = client.post("/execute", json={"command": "make a report"}).json()["task_id"]
        resp = client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert "status" in data

    def test_get_nonexistent_task_returns_404(self, client: TestClient):
        resp = client.get("/tasks/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_task_logs_endpoint_exists(self, client: TestClient):
        task_id = client.post("/execute", json={"command": "run a check"}).json()["task_id"]
        resp = client.get(f"/tasks/{task_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data

    def test_list_tasks_returns_list(self, client: TestClient):
        resp = client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_list_tasks_limit_parameter(self, client: TestClient):
        for _ in range(3):
            client.post("/execute", json={"command": "test command alpha"})
        resp = client.get("/tasks?limit=2")
        data = resp.json()
        assert len(data["tasks"]) <= 2

    def test_list_tasks_status_filter(self, client: TestClient):
        resp = client.get("/tasks?status=queued")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Memory / learnings
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryEndpoints:
    def test_learnings_endpoint_exists(self, client: TestClient):
        resp = client.get("/memory/learnings")
        assert resp.status_code == 200

    def test_learnings_returns_list(self, client: TestClient):
        data = client.get("/memory/learnings").json()
        assert "learnings" in data
        assert isinstance(data["learnings"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Custom tools
# ─────────────────────────────────────────────────────────────────────────────

class TestToolsEndpoints:
    def test_list_custom_tools(self, client: TestClient):
        resp = client.get("/tools/custom")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data

    def test_get_patterns(self, client: TestClient):
        resp = client.get("/tools/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert "patterns" in data


# ─────────────────────────────────────────────────────────────────────────────
# Schedules
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerEndpoints:
    def test_list_schedules(self, client: TestClient):
        resp = client.get("/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert "schedules" in data

    def test_create_schedule(self, client: TestClient):
        resp = client.post("/schedules", json={
            "name": "Test schedule",
            "command": "Check system health and log results",
            "cron": "0 9 * * *",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "schedule_id" in data
        assert "next_run_at" in data

    def test_delete_schedule(self, client: TestClient):
        sid = client.post("/schedules", json={
            "name": "Delete me",
            "command": "run test cleanup script",
            "cron": "0 0 * * *",
        }).json()["schedule_id"]
        resp = client.delete(f"/schedules/{sid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == sid

    def test_toggle_schedule(self, client: TestClient):
        sid = client.post("/schedules", json={
            "name": "Toggle test",
            "command": "run weekly analysis of workspace",
            "cron": "0 6 * * 1",
        }).json()["schedule_id"]
        resp = client.patch(f"/schedules/{sid}/toggle")
        assert resp.status_code == 200
        # Enabled field should have changed
        assert "enabled" in resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Monitor
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitorEndpoints:
    def test_metrics_endpoint(self, client: TestClient):
        resp = client.get("/monitor/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data
        assert "totals" in data
        assert "performance" in data

    def test_model_status_endpoint(self, client: TestClient):
        resp = client.get("/monitor/model-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "primary_model" in data
        assert "claude_circuit" in data

    def test_prompt_history_endpoint(self, client: TestClient):
        resp = client.get("/monitor/prompts/planning")
        assert resp.status_code == 200
        data = resp.json()
        assert "agent" in data
        assert "history" in data


# ─────────────────────────────────────────────────────────────────────────────
# Briefing
# ─────────────────────────────────────────────────────────────────────────────

class TestBriefingEndpoints:
    def test_briefing_post_accepted(self, client: TestClient):
        resp = client.post("/briefing", json={"hours": 24})
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_briefing_latest_shape(self, client: TestClient):
        """latest returns 404 (not yet written) or 200 with correct shape."""
        resp = client.get("/briefing/latest")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "headline" in data
            assert "health" in data

    def test_briefing_with_params(self, client: TestClient):
        resp = client.post("/briefing", json={"hours": 48, "recipients": []})
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectEndpoints:
    def test_list_projects_empty(self, client: TestClient):
        resp = client.get("/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data

    def test_create_project_returns_202(self, client: TestClient):
        resp = client.post("/projects", json={
            "name": "Test Project",
            "goal": "Build a complete test suite and verify all components work correctly",
            "auto_start": False,
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "project_id" in data

    def test_get_nonexistent_project_404(self, client: TestClient):
        resp = client.get("/projects/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_get_created_project(self, client: TestClient):
        pid = client.post("/projects", json={
            "name": "Fetch me",
            "goal": "Analyze all workspace files and generate a comprehensive summary report",
            "auto_start": False,
        }).json()["project_id"]
        resp = client.get(f"/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert "goal" in data


# ─────────────────────────────────────────────────────────────────────────────
# Stuck task recovery (startup)
# ─────────────────────────────────────────────────────────────────────────────

class TestStuckTaskRecovery:
    def test_recover_stuck_tasks_on_app_lifespan(self, client: TestClient):
        """New TestClient runs lifespan → recover_stuck_tasks fixes mid-flight rows."""
        from config import settings
        from fastapi.testclient import TestClient
        from main import app

        tid = str(uuid.uuid4())
        conn = sqlite3.connect(settings.db_path)
        conn.execute(
            """INSERT INTO tasks (task_id, command, status, source, created_at)
               VALUES (?,?,?,?,?)""",
            (tid, "recovery test command for stuck task", "executing", "api", datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        with TestClient(app) as c2:
            r = c2.get(f"/tasks/{tid}")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "failed"
            err = data.get("error") or ""
            assert "Server restarted" in err
            assert "retry" in err.lower()


@pytest.mark.asyncio
async def test_recover_stuck_tasks_returns_prior_status():
    import aiosqlite
    from config import settings
    import memory.store as store

    await store.init()
    tid = str(uuid.uuid4())
    await store.create_task(tid, "another recovery row", "api")
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute(
            "UPDATE tasks SET status=? WHERE task_id=?",
            ("planning", tid),
        )
        await db.commit()
    rows = await store.recover_stuck_tasks()
    assert any(r["task_id"] == tid and r["status"] == "planning" for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# Performance report
# ─────────────────────────────────────────────────────────────────────────────

class TestReportEndpoint:
    def test_report_returns_200_and_shape(self, client: TestClient):
        resp = client.get("/report?period=24h")
        assert resp.status_code == 200
        d = resp.json()
        assert d["period"] == "24h"
        assert "total_tasks" in d
        assert "success_rate" in d
        assert "avg_eval_score" in d
        assert "avg_loop_iterations" in d
        assert "top_goal_types" in d
        assert isinstance(d["top_goal_types"], list)
        assert "most_used_tools" in d
        assert isinstance(d["most_used_tools"], list)
        assert "custom_tools_built" in d
        assert "learnings_added" in d
        assert "total_tokens_saved" in d
        assert "model_usage" in d
        assert "claude" in d["model_usage"]
        assert "openai_fallback" in d["model_usage"]
        assert "worst_goal_type" in d
        assert "recommendation" in d
        assert isinstance(d["recommendation"], str)

    def test_report_invalid_period_400(self, client: TestClient):
        assert client.get("/report?period=invalid").status_code == 400
