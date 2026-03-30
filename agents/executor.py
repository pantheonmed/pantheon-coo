"""
agents/executor.py
──────────────────
Execution Agent — the "hands" of the COO.

Runs each step in the plan:
  - Respects depends_on ordering
  - Validates security before each step
  - Retries with exponential backoff
  - Collects typed results
  - Never crashes the loop — captures all errors as StepResult.FAILED
"""
from __future__ import annotations
import asyncio
import json
from typing import Any

from config import settings
from models import (
    ExecutionInput, ExecutionOutput, ExecutionStep,
    StepResult, StepStatus, ToolName,
)
from security.sandbox import SecurityError, validate_step
from tools import run_tool
import memory.store as store


class ExecutionAgent:
    name = "execution"

    async def run(self, inp: ExecutionInput) -> ExecutionOutput:
        results: dict[int, StepResult] = {}
        raw_outputs: dict[int, Any] = {}
        pending = list(inp.plan.steps)
        safety_limit = len(pending) + 5

        iteration = 0
        while pending and iteration < safety_limit:
            iteration += 1
            ready = [s for s in pending if self._deps_ok(s, results)]

            if not ready:
                # Deadlock — mark remaining as skipped
                for s in pending:
                    results[s.step_id] = StepResult(
                        step_id=s.step_id,
                        status=StepStatus.SKIPPED,
                        error="Dependency could not be satisfied",
                    )
                break

            wave = await asyncio.gather(
                *[self._run_with_retry(inp.task_id, s) for s in ready],
                return_exceptions=True,
            )

            for step, result in zip(ready, wave):
                if isinstance(result, Exception):
                    result = StepResult(
                        step_id=step.step_id,
                        status=StepStatus.FAILED,
                        error=str(result),
                    )
                results[step.step_id] = result
                if result.result is not None:
                    raw_outputs[step.step_id] = result.result
                pending.remove(step)

        all_results = list(results.values())
        succeeded = sum(1 for r in all_results if r.status == StepStatus.SUCCESS)
        failed    = sum(1 for r in all_results if r.status == StepStatus.FAILED)

        return ExecutionOutput(
            steps_run=len(all_results),
            succeeded=succeeded,
            failed=failed,
            results=all_results,
            raw_outputs=raw_outputs,
        )

    # ─────────────────────────────────────────────────────────────────

    async def _run_with_retry(self, task_id: str, step: ExecutionStep) -> StepResult:
        last_error: str | None = None
        tool_s = step.tool.value if hasattr(step.tool, "value") else str(step.tool)

        for attempt in range(settings.max_loop_iterations):  # reuse max_retries concept
            if attempt > 0:
                wait = min(2 ** attempt, 16)
                await store.log(task_id, f"Step {step.step_id} retry {attempt} (wait {wait}s)", "warning")
                await asyncio.sleep(wait)

            await store.push_stream_event(
                task_id,
                "step_start",
                {
                    "step_id": step.step_id,
                    "tool": tool_s,
                    "action": step.action,
                    "description": (step.description or "")[:200],
                    "attempt": attempt + 1,
                },
            )

            try:
                validate_step(step)
                await store.log(task_id, f"Step {step.step_id} → [{step.tool}] {step.action}", "info",
                                {"params": step.params})

                result = await run_tool(step.tool, step.action, step.params)

                await store.log(task_id, f"Step {step.step_id} ✓", "info",
                                {"result": _short(result)})
                await store.push_stream_event(
                    task_id,
                    "step_done",
                    {
                        "step_id": step.step_id,
                        "tool": tool_s,
                        "action": step.action,
                        "status": StepStatus.SUCCESS.value,
                        "preview": _short(result),
                        "error": None,
                    },
                )
                return StepResult(step_id=step.step_id, status=StepStatus.SUCCESS,
                                  result=result, retries_used=attempt)

            except SecurityError as e:
                await store.log(task_id, f"Step {step.step_id} SECURITY BLOCK: {e}", "error")
                await store.push_stream_event(
                    task_id,
                    "step_done",
                    {
                        "step_id": step.step_id,
                        "tool": tool_s,
                        "action": step.action,
                        "status": StepStatus.FAILED.value,
                        "preview": "",
                        "error": f"SECURITY: {e}",
                    },
                )
                return StepResult(step_id=step.step_id, status=StepStatus.FAILED,
                                  error=f"SECURITY: {e}", retries_used=attempt)

            except Exception as e:
                last_error = str(e)
                await store.log(task_id, f"Step {step.step_id} attempt {attempt+1} error: {e}", "warning")
                if attempt >= settings.max_loop_iterations - 1:
                    await store.push_stream_event(
                        task_id,
                        "step_done",
                        {
                            "step_id": step.step_id,
                            "tool": tool_s,
                            "action": step.action,
                            "status": StepStatus.FAILED.value,
                            "preview": "",
                            "error": last_error,
                        },
                    )

        return StepResult(step_id=step.step_id, status=StepStatus.FAILED,
                          error=last_error, retries_used=attempt)

    def _deps_ok(self, step: ExecutionStep, results: dict[int, StepResult]) -> bool:
        return all(
            results.get(dep) is not None
            and results[dep].status == StepStatus.SUCCESS
            for dep in step.depends_on
        )


def _short(val: Any) -> str:
    try:
        s = json.dumps(val, default=str)
        return s[:400]
    except Exception:
        return str(val)[:400]
