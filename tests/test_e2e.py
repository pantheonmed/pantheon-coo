"""
tests/test_e2e.py
──────────────────
End-to-end integration tests for the full Pantheon COO agent loop.

These tests run the complete Reason → Plan → Execute → Evaluate → Learn pipeline
against a real (temp) workspace with fully mocked Claude API responses.

They verify that the agents, orchestrator, memory store, and tool layer
all wire together correctly — catching integration bugs that unit tests miss.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py sets DB_PATH, WORKSPACE_DIR, ANTHROPIC_API_KEY, AUTH_MODE


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_claude(system_prompt_snippets: dict[str, str]):
    """
    Build a side_effect function that returns different JSON based on
    which agent is calling (identified by system prompt keywords).
    """
    def side_effect(*args, **kwargs):
        system = kwargs.get("system", "")
        for keyword, json_response in system_prompt_snippets.items():
            if keyword in system:
                mock_content = MagicMock()
                mock_content.text = json_response
                mock_response = MagicMock()
                mock_response.content = [mock_content]
                return mock_response
        # Default fallback
        mock_content = MagicMock()
        mock_content.text = '{"result": "ok"}'
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        return mock_response
    return side_effect


WRITE_FILE_PLAN = json.dumps({
    "goal_summary": "Write hello.txt to workspace",
    "estimated_seconds": 3,
    "notes": "",
    "steps": [
        {
            "step_id": 1,
            "tool": "filesystem",
            "action": "make_dir",
            "params": {"path": "/tmp/pantheon_v2/e2e_output"},
            "depends_on": [],
            "description": "Ensure output directory exists",
        },
        {
            "step_id": 2,
            "tool": "filesystem",
            "action": "write_file",
            "params": {
                "path": "/tmp/pantheon_v2/e2e_output/hello.txt",
                "content": "Hello from Pantheon COO!",
            },
            "depends_on": [1],
            "description": "Write the hello file",
        },
    ],
})

TERMINAL_PLAN = json.dumps({
    "goal_summary": "List workspace contents",
    "estimated_seconds": 2,
    "notes": "",
    "steps": [
        {
            "step_id": 1,
            "tool": "terminal",
            "action": "run_command",
            "params": {"command": "ls /tmp/pantheon_v2"},
            "depends_on": [],
            "description": "List the workspace directory",
        }
    ],
})

REASONING = json.dumps({
    "understood_goal": "Write a hello file to the workspace",
    "goal_type": "build",
    "complexity": "low",
    "risks": [],
    "constraints": [],
    "success_criteria": ["File hello.txt exists in workspace"],
    "clarifications_needed": [],
})

EVALUATOR_PASS = json.dumps({
    "score": 0.95,
    "goal_met": True,
    "what_worked": ["Files created successfully"],
    "what_failed": [],
    "improvement_hints": [],
    "summary": "Task completed. File written to workspace as expected.",
})

EVALUATOR_FAIL = json.dumps({
    "score": 0.30,
    "goal_met": False,
    "what_worked": [],
    "what_failed": ["File was not created"],
    "improvement_hints": ["Verify workspace path exists before writing"],
    "summary": "File was not found in the expected location.",
})

MEMORY_OUT = json.dumps({
    "stored": True,
    "learning": "Always create parent directories before writing files.",
})

CONFIDENCE_HIGH = json.dumps({
    "score": 0.92,
    "level": "high",
    "reasoning": "Clear goal with well-defined steps.",
    "flags": [],
})


# ─────────────────────────────────────────────────────────────────────────────
# Full loop — success path
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorLoop:
    @pytest.mark.asyncio
    async def test_successful_task_reaches_done(self):
        """Full loop: queue → reasoning → planning → execution → evaluation → done."""
        task_id = str(uuid.uuid4())

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = _mock_claude({
                "Reasoning Agent": REASONING,
                "Planning Agent": WRITE_FILE_PLAN,
                "Evaluator Agent": EVALUATOR_PASS,
                "Memory Agent": MEMORY_OUT,
                "confidence evaluator": CONFIDENCE_HIGH,
            })
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.init()
            await store.init_projects()
            await store.create_task(task_id, "Write hello.txt to workspace", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="Write hello.txt to workspace",
                context={},
                dry_run=False,
            )

        row = await store.get_task(task_id)
        assert row is not None
        assert row["status"] == "done", f"Expected done, got {row['status']}: {row.get('error')}"
        assert row["eval_score"] is not None
        assert row["eval_score"] >= 0.75
        assert row["loop_iterations"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_skips_execution(self):
        """Dry run produces a plan but never calls the execution engine."""
        task_id = str(uuid.uuid4())

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = _mock_claude({
                "Reasoning Agent": REASONING,
                "Planning Agent": WRITE_FILE_PLAN,
                "confidence evaluator": CONFIDENCE_HIGH,
            })
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.create_task(task_id, "Write a report", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="Write a report",
                context={},
                dry_run=True,
            )

        row = await store.get_task(task_id)
        assert row["status"] == "done"
        assert row["eval_score"] is None  # no evaluation on dry run

    @pytest.mark.asyncio
    async def test_task_memory_is_stored(self):
        """After a successful task, a learning should be stored in DB."""
        task_id = str(uuid.uuid4())

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = _mock_claude({
                "Reasoning Agent": REASONING,
                "Planning Agent": WRITE_FILE_PLAN,
                "Evaluator Agent": EVALUATOR_PASS,
                "Memory Agent": MEMORY_OUT,
                "confidence evaluator": CONFIDENCE_HIGH,
            })
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.create_task(task_id, "Write output file", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="Write output file",
                context={},
                dry_run=False,
            )

        learnings = await store.get_learnings("build", limit=10)
        assert any("director" in l.lower() or "mkdir" in l.lower() or "parent" in l.lower()
                   for l in learnings), f"Expected mkdir learning, got: {learnings}"

    @pytest.mark.asyncio
    async def test_failed_evaluation_loops(self):
        """When evaluator says goal_met=False, orchestrator runs another iteration."""
        task_id = str(uuid.uuid4())
        call_counts = {"eval": 0}

        def counting_side_effect(*args, **kwargs):
            system = kwargs.get("system", "")
            mock_content = MagicMock()
            if "Evaluator Agent" in system:
                call_counts["eval"] += 1
                # Fail first time, pass second time
                if call_counts["eval"] == 1:
                    mock_content.text = EVALUATOR_FAIL
                else:
                    mock_content.text = EVALUATOR_PASS
            elif "Reasoning Agent" in system:
                mock_content.text = REASONING
            elif "Planning Agent" in system:
                mock_content.text = WRITE_FILE_PLAN
            elif "Memory Agent" in system:
                mock_content.text = MEMORY_OUT
            elif "confidence evaluator" in system:
                mock_content.text = CONFIDENCE_HIGH
            else:
                mock_content.text = '{"result": "ok"}'
            mock_response = MagicMock()
            mock_response.content = [mock_content]
            return mock_response

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = counting_side_effect
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.create_task(task_id, "Write output with retry", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="Write output with retry",
                context={},
                dry_run=False,
            )

        row = await store.get_task(task_id)
        # Should have looped: evaluator called at least twice
        assert call_counts["eval"] >= 2
        assert row["loop_iterations"] >= 2

    @pytest.mark.asyncio
    async def test_terminal_tool_executes_real_command(self):
        """A plan using the terminal tool actually runs the command."""
        task_id = str(uuid.uuid4())

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = _mock_claude({
                "Reasoning Agent": REASONING,
                "Planning Agent": TERMINAL_PLAN,
                "Evaluator Agent": EVALUATOR_PASS,
                "Memory Agent": MEMORY_OUT,
                "confidence evaluator": CONFIDENCE_HIGH,
            })
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.create_task(task_id, "List workspace", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="List workspace",
                context={},
                dry_run=False,
            )

        row = await store.get_task(task_id)
        results = json.loads(row.get("results_json") or "[]")
        assert len(results) > 0
        terminal_results = [r for r in results if r.get("status") == "success"]
        assert len(terminal_results) > 0

    @pytest.mark.asyncio
    async def test_task_logs_populated(self):
        """Execution logs should contain entries for each agent phase."""
        task_id = str(uuid.uuid4())

        with patch("anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.messages.create.side_effect = _mock_claude({
                "Reasoning Agent": REASONING,
                "Planning Agent": WRITE_FILE_PLAN,
                "Evaluator Agent": EVALUATOR_PASS,
                "Memory Agent": MEMORY_OUT,
                "confidence evaluator": CONFIDENCE_HIGH,
            })
            mock_cls.return_value = mock_instance

            import memory.store as store
            await store.create_task(task_id, "Generate a summary doc", "test")

            import orchestrator
            await orchestrator.run(
                task_id=task_id,
                command="Generate a summary doc",
                context={},
                dry_run=False,
            )

        logs = await store.get_logs(task_id)
        messages = [l["message"] for l in logs]
        assert any("Understood goal" in m for m in messages), "Missing reasoning log"
        assert any("Plan" in m for m in messages), "Missing planning log"
        assert any("DONE" in m or "complete" in m.lower() for m in messages), "Missing completion log"


# ─────────────────────────────────────────────────────────────────────────────
# API retry endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryEndpoint:
    def test_retry_failed_task(self, client):
        """POST /tasks/{id}/retry on a failed task creates a new task."""
        # Create and mark a task as failed
        resp = client.post("/execute", json={"command": "write a test report file"})
        task_id = resp.json()["task_id"]

        # Manually set it to failed via direct DB write
        async def mark_failed():
            import memory.store as store
            from models import TaskStatus
            await store.update_status(task_id, TaskStatus.FAILED,
                                      summary="Simulated failure", error="timeout")

        asyncio.get_event_loop().run_until_complete(mark_failed())

        retry_resp = client.post(f"/tasks/{task_id}/retry")
        assert retry_resp.status_code == 202
        data = retry_resp.json()
        assert "task_id" in data
        assert data["task_id"] != task_id  # new task ID
        assert "retry" in data.get("summary", "").lower()

    def test_retry_queued_task_rejected(self, client):
        """Cannot retry a task that is still queued/running."""
        resp = client.post("/execute", json={"command": "analyze project structure"})
        task_id = resp.json()["task_id"]
        # Task is in 'queued' status immediately after submit
        retry_resp = client.post(f"/tasks/{task_id}/retry")
        assert retry_resp.status_code == 400

    def test_retry_nonexistent_task_404(self, client):
        """Retry of a non-existent task returns 404."""
        resp = client.post("/tasks/00000000-0000-0000-0000-000000000000/retry")
        assert resp.status_code == 404
