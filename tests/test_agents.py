"""
tests/test_agents.py
─────────────────────
Unit tests for agent logic, memory store, and pattern detector.
No real Claude calls — all mocked via conftest.py.
"""
import asyncio
import json
import os
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Models — ensure all Pydantic models instantiate correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestModels:
    def test_execution_step_defaults(self):
        from models import ExecutionStep, ToolName, StepStatus
        step = ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM, action="read_file")
        assert step.status == StepStatus.PENDING
        assert step.depends_on == []
        assert step.retry_count == 0

    def test_planning_output_instantiation(self):
        from models import PlanningOutput, ExecutionStep, ToolName
        plan = PlanningOutput(
            goal_summary="Test goal",
            steps=[
                ExecutionStep(step_id=1, tool=ToolName.TERMINAL,
                              action="run_command", params={"command": "pwd"})
            ],
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == ToolName.TERMINAL

    def test_reasoning_output_instantiation(self):
        from models import ReasoningOutput
        r = ReasoningOutput(
            understood_goal="Create a file",
            goal_type="build",
            complexity="low",
            success_criteria=["File exists"],
        )
        assert r.complexity == "low"
        assert r.clarifications_needed == []

    @pytest.mark.asyncio
    async def test_reasoning_fallback_when_model_returns_invalid_json(self):
        from unittest.mock import patch

        from agents.model_router import ModelResponse
        from agents.reasoning import ReasoningAgent
        from models import ReasoningInput

        bad = ModelResponse(
            text="<<<not-valid-json>>>",
            model_used="test-model",
            provider="anthropic",
            fallback_used=False,
        )
        with patch("agents.reasoning.call_model", return_value=bad):
            out = await ReasoningAgent().run(ReasoningInput(raw_goal="Ship feature X"))
        assert out.understood_goal == "Ship feature X"
        assert out.goal_type == "build"
        assert out.complexity == "medium"
        assert any("parse" in r.lower() or "attempts" in r.lower() for r in out.risks)

    def test_evaluator_output_goal_met_logic(self):
        from models import EvaluatorOutput
        e = EvaluatorOutput(score=0.9, goal_met=True)
        assert e.goal_met is True
        assert e.score == 0.9
        assert e.auto_checks == []
        assert e.auto_check_override is False

    def test_command_request_min_length(self):
        from pydantic import ValidationError
        from models import CommandRequest
        with pytest.raises(ValidationError):
            CommandRequest(command="ab")  # too short

    def test_task_status_enum_values(self):
        from models import TaskStatus
        assert TaskStatus.QUEUED.value == "queued"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.FAILED.value == "failed"

    def test_project_request_model(self):
        from models import ProjectRequest
        req = ProjectRequest(name="My Project", goal="Build something amazing and useful")
        assert req.auto_start is True
        assert req.context == {}


# ─────────────────────────────────────────────────────────────────────────────
# Memory store
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_init_creates_tables(self):
        from memory.store import init
        await init()  # should not raise

    @pytest.mark.asyncio
    async def test_create_and_get_task(self):
        from memory.store import init, create_task, get_task
        await init()
        await create_task("test-task-001", "Test command", "cli")
        row = await get_task("test-task-001")
        assert row is not None
        assert row["command"] == "Test command"
        assert row["status"] == "queued"
        assert row["source"] == "cli"

    @pytest.mark.asyncio
    async def test_update_task_status(self):
        from memory.store import init, create_task, update_status, get_task
        from models import TaskStatus
        await init()
        await create_task("test-task-002", "Another command", "api")
        await update_status("test-task-002", TaskStatus.DONE, summary="completed ok")
        row = await get_task("test-task-002")
        assert row["status"] == "done"
        assert row["summary"] == "completed ok"
        assert row["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_save_and_get_learning(self):
        from memory.store import init, save_learning, get_learnings
        await init()
        await save_learning("task-abc", "build", "Always mkdir before writing files.", 0.9)
        learnings = await get_learnings("build", limit=5)
        assert any("mkdir" in l for l in learnings)

    @pytest.mark.asyncio
    async def test_log_and_retrieve(self):
        from memory.store import init, create_task, log, get_logs
        await init()
        await create_task("log-test-001", "logging test", "api")
        await log("log-test-001", "Step 1 started", "info")
        await log("log-test-001", "Step 1 failed", "error", {"code": 1})
        logs = await get_logs("log-test-001")
        assert len(logs) == 2
        assert logs[0]["level"] == "info"
        assert logs[1]["level"] == "error"

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        from memory.store import init, create_task, list_tasks
        await init()
        await create_task("list-t-001", "cmd one", "api")
        await create_task("list-t-002", "cmd two", "cli")
        tasks = await list_tasks(limit=50)
        ids = [t["task_id"] for t in tasks]
        assert "list-t-001" in ids
        assert "list-t-002" in ids

    @pytest.mark.asyncio
    async def test_get_stats(self):
        from memory.store import init, get_stats
        await init()
        stats = await get_stats()
        assert "total" in stats
        assert "learnings" in stats

    @pytest.mark.asyncio
    async def test_nonexistent_task_returns_none(self):
        from memory.store import init, get_task
        await init()
        assert await get_task("does-not-exist") is None


# ─────────────────────────────────────────────────────────────────────────────
# Pattern detector
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternDetector:
    def test_fingerprint_same_plan_consistent(self):
        from pattern_detector import _fingerprint
        from models import PlanningOutput, ExecutionStep, ToolName

        def make_plan():
            return PlanningOutput(
                goal_summary="test",
                steps=[
                    ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM,
                                  action="make_dir", params={"path": "/tmp/x"}),
                    ExecutionStep(step_id=2, tool=ToolName.TERMINAL,
                                  action="run_command", params={"command": "ls"}),
                ],
            )

        fp1 = _fingerprint(make_plan())
        fp2 = _fingerprint(make_plan())
        assert fp1 == fp2  # same structure → same fingerprint

    def test_fingerprint_different_params_same_shape(self):
        from pattern_detector import _fingerprint
        from models import PlanningOutput, ExecutionStep, ToolName

        plan_a = PlanningOutput(goal_summary="a", steps=[
            ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM, action="write_file",
                          params={"path": "/tmp/a.txt", "content": "hello"})
        ])
        plan_b = PlanningOutput(goal_summary="b", steps=[
            ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM, action="write_file",
                          params={"path": "/tmp/b.txt", "content": "world"})
        ])
        # Same tool+action shape — fingerprints should match
        assert _fingerprint(plan_a) == _fingerprint(plan_b)

    def test_fingerprint_different_tools_differ(self):
        from pattern_detector import _fingerprint
        from models import PlanningOutput, ExecutionStep, ToolName

        plan_fs = PlanningOutput(goal_summary="x", steps=[
            ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM, action="read_file",
                          params={"path": "/tmp/x"})
        ])
        plan_term = PlanningOutput(goal_summary="x", steps=[
            ExecutionStep(step_id=1, tool=ToolName.TERMINAL, action="run_command",
                          params={"command": "ls"})
        ])
        assert _fingerprint(plan_fs) != _fingerprint(plan_term)

    def test_describe_pattern_readable(self):
        from pattern_detector import _fingerprint, describe_pattern
        from models import PlanningOutput, ExecutionStep, ToolName

        plan = PlanningOutput(goal_summary="x", steps=[
            ExecutionStep(step_id=1, tool=ToolName.FILESYSTEM, action="write_file",
                          params={"path": "/tmp/x"}),
            ExecutionStep(step_id=2, tool=ToolName.TERMINAL, action="run_command",
                          params={"command": "python3 x.py"}),
        ])
        fp = _fingerprint(plan)
        desc = describe_pattern(fp)
        assert "filesystem.write_file" in desc
        assert "terminal.run_command" in desc
        assert "→" in desc


# ─────────────────────────────────────────────────────────────────────────────
# Grounded evaluator — auto-checks (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

class TestGroundedEvaluator:
    def test_write_file_passes_when_file_exists(self, tmp_path):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        p = tmp_path / "written.txt"
        p.write_text("ok")
        plan = PlanningOutput(
            goal_summary="write",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.FILESYSTEM,
                    action="write_file",
                    params={"path": str(p)},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"path": str(p), "bytes": 2},
                ),
            ],
        )
        checks, failed = run_ground_checks(plan, ex)
        assert failed is False
        assert len(checks) == 1
        assert checks[0]["check_type"] == "filesystem_write"
        assert checks[0]["passed"] is True
        assert "path" in checks[0]["detail"].lower() or "present" in checks[0]["detail"].lower()

    def test_write_file_fails_when_file_missing(self, tmp_path):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        p = tmp_path / "nowhere.txt"
        plan = PlanningOutput(
            goal_summary="write",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.FILESYSTEM,
                    action="write_file",
                    params={"path": str(p)},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"path": str(p), "bytes": 0},
                ),
            ],
        )
        checks, failed = run_ground_checks(plan, ex)
        assert failed is True
        assert checks[0]["passed"] is False
        assert checks[0]["check_type"] == "filesystem_write"

    def test_terminal_exit_zero_passes(self):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        plan = PlanningOutput(
            goal_summary="cmd",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.TERMINAL,
                    action="run_command",
                    params={"command": "true"},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"exit_code": 0, "stdout": "", "stderr": "", "success": True},
                ),
            ],
        )
        checks, failed = run_ground_checks(plan, ex)
        assert failed is False
        assert checks[0]["check_type"] == "terminal_exit"
        assert checks[0]["passed"] is True

    def test_terminal_nonzero_fails(self):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        plan = PlanningOutput(
            goal_summary="cmd",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.TERMINAL,
                    action="run_command",
                    params={"command": "false"},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"exit_code": 1, "stdout": "", "stderr": "no", "success": False},
                ),
            ],
        )
        _, failed = run_ground_checks(plan, ex)
        assert failed is True

    def test_http_status_ok(self):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        plan = PlanningOutput(
            goal_summary="get",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.HTTP,
                    action="get",
                    params={"url": "https://example.com"},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"status_code": 200, "ok": True, "body": "", "url": "https://example.com/"},
                ),
            ],
        )
        checks, failed = run_ground_checks(plan, ex)
        assert failed is False
        assert checks[0]["check_type"] == "http_status"
        assert checks[0]["passed"] is True

    def test_http_status_4xx_fails(self):
        from agents.evaluator import run_ground_checks
        from models import (
            PlanningOutput, ExecutionStep, ToolName,
            ExecutionOutput, StepResult, StepStatus,
        )

        plan = PlanningOutput(
            goal_summary="get",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.HTTP,
                    action="get",
                    params={"url": "https://example.com/missing"},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"status_code": 404, "ok": False, "body": "", "url": "https://example.com/x"},
                ),
            ],
        )
        _, failed = run_ground_checks(plan, ex)
        assert failed is True

    def test_apply_ground_cap_high_score(self):
        from agents.evaluator import apply_ground_cap
        from models import EvaluatorOutput

        out = EvaluatorOutput(score=0.99, goal_met=True, summary="ok")
        capped = apply_ground_cap(out, True)
        assert capped.score == 0.5
        assert capped.goal_met is False
        assert capped.auto_check_override is True

    def test_cap_score_when_write_file_missing(self, tmp_path):
        from agents.evaluator import run_ground_checks, apply_ground_cap
        from models import EvaluatorOutput, PlanningOutput, ExecutionStep, ToolName
        from models import ExecutionOutput, StepResult, StepStatus

        p = tmp_path / "ghost.txt"
        plan = PlanningOutput(
            goal_summary="w",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.FILESYSTEM,
                    action="write_file",
                    params={"path": str(p)},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"path": str(p), "bytes": 0},
                ),
            ],
        )
        checks, failed = run_ground_checks(plan, ex)
        assert failed is True
        out = EvaluatorOutput(score=0.9, goal_met=True, summary="ok", auto_checks=checks)
        capped = apply_ground_cap(out, True)
        assert capped.score == min(0.9, 0.5)
        assert capped.auto_check_override is True

    def test_cap_score_when_terminal_exit_nonzero(self):
        from agents.evaluator import run_ground_checks, apply_ground_cap
        from models import EvaluatorOutput, PlanningOutput, ExecutionStep, ToolName
        from models import ExecutionOutput, StepResult, StepStatus

        plan = PlanningOutput(
            goal_summary="t",
            steps=[
                ExecutionStep(
                    step_id=2,
                    tool=ToolName.TERMINAL,
                    action="run_command",
                    params={"command": "false"},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=2,
                    status=StepStatus.SUCCESS,
                    result={"exit_code": 1, "stdout": "", "stderr": "x", "success": False},
                ),
            ],
        )
        _, failed = run_ground_checks(plan, ex)
        assert failed is True
        out = EvaluatorOutput(score=0.88, goal_met=True)
        capped = apply_ground_cap(out, True)
        assert capped.score == 0.5
        assert capped.auto_check_override is True

    def test_no_cap_when_all_ground_checks_pass(self, tmp_path):
        from agents.evaluator import run_ground_checks, apply_ground_cap
        from models import EvaluatorOutput, PlanningOutput, ExecutionStep, ToolName
        from models import ExecutionOutput, StepResult, StepStatus

        p = tmp_path / "ok.txt"
        p.write_text("hi")
        plan = PlanningOutput(
            goal_summary="ok",
            steps=[
                ExecutionStep(
                    step_id=1,
                    tool=ToolName.FILESYSTEM,
                    action="write_file",
                    params={"path": str(p)},
                ),
            ],
        )
        ex = ExecutionOutput(
            steps_run=1,
            succeeded=1,
            failed=0,
            results=[
                StepResult(
                    step_id=1,
                    status=StepStatus.SUCCESS,
                    result={"path": str(p), "bytes": 2},
                ),
            ],
        )
        _, failed = run_ground_checks(plan, ex)
        assert failed is False
        out = EvaluatorOutput(score=0.95, goal_met=True, summary="great")
        same = apply_ground_cap(out, False)
        assert same.score == 0.95
        assert same.goal_met is True
        assert same.auto_check_override is False


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler cron parser
# ─────────────────────────────────────────────────────────────────────────────

class TestCronParser:
    def test_every_hour(self):
        from scheduler import _next_run
        from datetime import timezone
        nxt = _next_run("0 * * * *")
        assert nxt.tzinfo is not None
        assert nxt.minute == 0

    def test_daily_9am(self):
        from scheduler import _next_run
        nxt = _next_run("0 9 * * *")
        assert nxt.hour == 9
        assert nxt.minute == 0

    def test_step_syntax(self):
        from scheduler import _next_run
        nxt = _next_run("*/15 * * * *")
        assert nxt.minute % 15 == 0

    def test_invalid_cron_defaults(self):
        from scheduler import _next_run
        # invalid cron falls back to every-hour default
        nxt = _next_run("not valid at all")
        assert nxt is not None  # just doesn't crash
