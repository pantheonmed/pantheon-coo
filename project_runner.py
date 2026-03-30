"""
project_runner.py
──────────────────
Phase 5 — Parallel Project Executor

Runs a decomposed project's sub-tasks through the orchestrator,
respecting dependency ordering and maximising parallelism.

Execution model:
  - Sub-tasks with no unmet dependencies run concurrently (wave-based)
  - Each sub-task is a full orchestrator.run() call (Reason→Plan→Execute→Evaluate)
  - Progress is tracked in the projects DB table
  - High-priority tasks are surfaced first within each wave
  - Failures are isolated: one sub-task failing doesn't block independent ones

This gives the COO the ability to work on multiple things simultaneously,
just like a real COO delegates to different team members in parallel.
"""
from __future__ import annotations
import asyncio
import json
import uuid
from datetime import datetime

import memory.store as store
from models import SubTask, ProjectStatus
import orchestrator


async def run_project(
    project_id: str,
    sub_tasks: list[SubTask],
    context: dict,
) -> dict:
    """
    Execute all sub-tasks for a project with dependency-aware parallelism.
    Returns a summary dict with per-subtask outcomes.
    """
    await store.log(
        project_id,
        f"Project started: {len(sub_tasks)} sub-tasks",
        "info",
    )

    # Map sub_task_id → (task_id, status)
    results: dict[int, dict] = {}
    pending = sorted(sub_tasks, key=lambda s: (-s.priority, s.sub_task_id))
    max_waves = len(pending) + 3

    wave = 0
    while pending and wave < max_waves:
        wave += 1

        # Collect sub-tasks whose dependencies are all done
        ready = [
            s for s in pending
            if all(
                results.get(dep, {}).get("status") == "done"
                for dep in s.depends_on
            )
        ]

        if not ready:
            # Check for deadlock (blocked by failed dependencies)
            deadlocked = [
                s for s in pending
                if any(
                    results.get(dep, {}).get("status") == "failed"
                    for dep in s.depends_on
                )
            ]
            for s in deadlocked:
                results[s.sub_task_id] = {
                    "task_id": None, "status": "skipped",
                    "reason": "dependency failed",
                }
                pending.remove(s)
            if not pending:
                break
            # Genuine deadlock — shouldn't happen with valid DAG
            await store.log(project_id, f"Wave {wave}: dependency deadlock detected", "warning")
            break

        await store.log(
            project_id,
            f"Wave {wave}: launching {len(ready)} sub-task(s) in parallel "
            f"[{', '.join(str(s.sub_task_id) for s in ready)}]",
            "info",
        )

        # Launch all ready sub-tasks concurrently
        wave_coros = [
            _run_sub_task(project_id, s, context)
            for s in ready
        ]
        wave_results = await asyncio.gather(*wave_coros, return_exceptions=True)

        for sub_task, result in zip(ready, wave_results):
            if isinstance(result, Exception):
                results[sub_task.sub_task_id] = {
                    "task_id": None, "status": "failed", "error": str(result)
                }
            else:
                results[sub_task.sub_task_id] = result
            pending.remove(sub_task)

        # Update project progress
        progress = await store.update_project_progress(project_id)
        await store.log(
            project_id, f"Progress: {progress:.0%}", "info"
        )

    # Final summary
    done  = sum(1 for r in results.values() if r.get("status") == "done")
    failed = sum(1 for r in results.values() if r.get("status") == "failed")
    skipped = sum(1 for r in results.values() if r.get("status") == "skipped")

    final_status = (
        ProjectStatus.COMPLETED if failed == 0 and skipped == 0
        else ProjectStatus.FAILED if done == 0
        else ProjectStatus.ACTIVE  # partial — some failed, some done
    )

    await store.log(
        project_id,
        f"Project complete: {done} done, {failed} failed, {skipped} skipped",
        "info" if failed == 0 else "warning",
    )

    return {
        "project_id": project_id,
        "status": final_status.value,
        "done": done,
        "failed": failed,
        "skipped": skipped,
        "sub_task_results": results,
    }


async def _run_sub_task(
    project_id: str,
    sub_task: SubTask,
    context: dict,
) -> dict:
    """Run a single sub-task through the full orchestrator loop."""
    task_id = str(uuid.uuid4())

    await store.create_task(
        task_id,
        sub_task.command,
        source=f"project:{project_id}:sub{sub_task.sub_task_id}",
    )
    await store.add_task_to_project(project_id, task_id)

    try:
        await orchestrator.run(
            task_id=task_id,
            command=sub_task.command,
            context={**context, "project_id": project_id,
                     "sub_task_id": sub_task.sub_task_id},
            dry_run=False,
        )

        row = await store.get_task(task_id)
        final_status = (row or {}).get("status", "failed")
        eval_score = (row or {}).get("eval_score")

        return {
            "task_id": task_id,
            "status": final_status,
            "eval_score": eval_score,
        }

    except Exception as e:
        return {"task_id": task_id, "status": "failed", "error": str(e)}
