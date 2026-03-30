"""
agents/evaluator.py
───────────────────
Evaluator Agent — the COO's quality control layer.

After every execution, the Evaluator:
  1. Scores how well the outcome matches the original goal (0.0–1.0)
  2. Checks each success criterion defined by the Reasoning Agent
  3. Identifies what worked and what failed
  4. Provides actionable improvement hints for the next loop iteration
  5. Makes the final call: DONE or RETRY?
  6. Runs grounded auto-checks on filesystem / terminal / HTTP results

This is what separates a COO from a simple script runner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from config import settings
import memory.store as store
from models import (
    EvaluatorInput,
    EvaluatorOutput,
    ExecutionOutput,
    PlanningOutput,
    StepResult,
    StepStatus,
    ToolName,
)


SYSTEM = """
You are the Evaluator Agent of Pantheon COO OS — an autonomous AI Chief Operating Officer.

Your role: objectively assess whether a task was completed successfully.

Given the original goal, success criteria, execution plan, and results, you must:
1. Score the outcome from 0.0 (complete failure) to 1.0 (perfect success)
2. Check each success criterion: was it met?
3. List what worked well
4. List what failed or was incomplete
5. Provide specific, actionable hints for the next attempt (if score < threshold)
6. Decide: goal_met = true if score >= 0.75, false otherwise

Be honest and precise. A score of 0.8 means 80% of the goal was achieved.
Do NOT give a high score just because steps ran — check if the OUTPUT is actually correct.

OUTPUT: valid JSON only:
{
  "score": 0.0-1.0,
  "goal_met": true|false,
  "what_worked": ["string"],
  "what_failed": ["string"],
  "improvement_hints": ["specific hint for next attempt"],
  "summary": "2 sentence plain English summary of what happened"
}

No markdown. No text outside JSON.
"""


def _result_as_dict(val: Any) -> dict[str, Any] | None:
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def run_ground_checks(plan: PlanningOutput, execution: ExecutionOutput) -> tuple[list[dict[str, Any]], bool]:
    """
    Verify concrete outcomes for successful steps.

    Each entry: {check_type, step_id, passed, detail}
    check_type: filesystem_write | terminal_exit | http_status
    Returns (auto_checks, any_failed).
    """
    by_step: dict[int, StepResult] = {r.step_id: r for r in execution.results}
    checks: list[dict[str, Any]] = []
    any_failed = False

    for step in plan.steps:
        sr = by_step.get(step.step_id)
        if sr is None or sr.status != StepStatus.SUCCESS:
            continue

        tool = step.tool
        raw = sr.result

        if tool == ToolName.FILESYSTEM and step.action == "write_file":
            params = step.params or {}
            path_str = params.get("path") or ""
            rd = _result_as_dict(raw)
            if not path_str and rd:
                path_str = str(rd.get("path") or "")
            p = Path(path_str) if path_str else None
            ok = bool(p and p.is_file())
            detail = (
                f"File present at {path_str}" if ok else f"File missing at {path_str or '(no path)'}"
            )
            checks.append({
                "check_type": "filesystem_write",
                "step_id": step.step_id,
                "passed": ok,
                "detail": detail,
            })
            if not ok:
                any_failed = True

        elif tool == ToolName.TERMINAL and step.action == "run_command":
            rd = _result_as_dict(raw)
            exit_code = rd.get("exit_code") if rd else None
            success_flag = rd.get("success") if rd else None
            ok = exit_code == 0 if exit_code is not None else (success_flag is True)
            detail = (
                f"exit_code=0" if ok else f"exit_code={exit_code!r} (expected 0)"
            )
            checks.append({
                "check_type": "terminal_exit",
                "step_id": step.step_id,
                "passed": ok,
                "detail": detail,
            })
            if not ok:
                any_failed = True

        elif tool == ToolName.HTTP:
            rd = _result_as_dict(raw)
            code = rd.get("status_code") if rd else None
            ok = isinstance(code, int) and code < 400
            detail = (
                f"HTTP status {code} (<400)" if ok else f"HTTP status {code!r} (>=400)"
            )
            checks.append({
                "check_type": "http_status",
                "step_id": step.step_id,
                "passed": ok,
                "detail": detail,
            })
            if not ok:
                any_failed = True

    return checks, any_failed


def apply_ground_cap(out: EvaluatorOutput, any_auto_failed: bool) -> EvaluatorOutput:
    """Cap score to min(Claude score, 0.5) when grounded checks fail."""
    if not any_auto_failed:
        return out
    new_score = min(out.score, 0.5)
    goal_met = new_score >= settings.min_eval_score
    return out.model_copy(
        update={
            "score": new_score,
            "goal_met": goal_met,
            "auto_check_override": True,
        },
    )


class EvaluatorAgent(BaseAgent[EvaluatorInput, EvaluatorOutput]):
    name = "evaluator"
    system_prompt = SYSTEM
    model = settings.claude_model_fast   # faster/cheaper for evaluation
    max_tokens = 1024

    async def run(self, inp: EvaluatorInput) -> EvaluatorOutput:
        results_summary = []
        for r in inp.execution.results:
            results_summary.append({
                "step_id": r.step_id,
                "status": r.status.value,
                "result_preview": _truncate(r.result),
                "error": r.error,
            })

        msg = f"""Goal: {inp.goal}

Success criteria:
{json.dumps(inp.success_criteria, indent=2)}

Plan summary ({len(inp.plan.steps)} steps):
{inp.plan.goal_summary}

Execution results:
- Total steps: {inp.execution.steps_run}
- Succeeded: {inp.execution.succeeded}
- Failed: {inp.execution.failed}

Step details:
{json.dumps(results_summary, indent=2, default=str)}

Evaluate and return the JSON now."""

        out = await self._call_claude_async(msg, EvaluatorOutput)
        auto_checks, failed = run_ground_checks(inp.plan, inp.execution)
        out = out.model_copy(update={"auto_checks": auto_checks})
        if failed:
            if inp.task_id:
                for c in auto_checks:
                    if not c.get("passed"):
                        await store.log(
                            inp.task_id,
                            f"Auto-check FAILED: {c.get('detail')} — score capped at 0.50",
                            "warning",
                        )
            out = apply_ground_cap(out, True)
        return out


def _truncate(val, max_len=300) -> str:
    if val is None:
        return ""
    try:
        s = json.dumps(val, default=str)
        return s[:max_len] + "..." if len(s) > max_len else s
    except Exception:
        return str(val)[:max_len]
