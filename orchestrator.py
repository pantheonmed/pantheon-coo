"""
orchestrator.py
───────────────
The Orchestrator is the heart of Pantheon COO OS.

It runs the autonomous agent loop:

  ┌──────────────────────────────────────────────────────────────┐
  │  Goal                                                        │
  │   → Reasoning Agent  (understand + define success criteria)  │
  │   → Memory recall    (inject past learnings)                 │
  │   → Planning Agent   (goal → typed execution steps)          │
  │   → Execution Agent  (run steps, retry on failure)           │
  │   → Evaluator Agent  (score quality, decide: done or retry?) │
  │   → Memory Agent     (store learning for future tasks)       │
  │   → if not done and iterations < max: loop back              │
  └──────────────────────────────────────────────────────────────┘

The loop is what makes this a COO, not a chatbot.
"""
from __future__ import annotations
import json
import asyncio
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings
from models import (
    TaskStatus, TaskRecord, CommandResponse,
    ReasoningInput, PlanningInput, ExecutionInput,
    EvaluatorInput, MemoryInput,
    PlanningOutput, ExecutionOutput, EvaluatorOutput,
)
from agents import (
    ReasoningAgent, PlanningAgent, ExecutionAgent,
    EvaluatorAgent, MemoryAgent,
)
from agents.memory_agent import recall_relevant
import memory.store as store
from pattern_detector import record_and_detect
from agents.tool_builder import maybe_build_tool
from agents.confidence import score_reasoning, score_plan
from agents.prompt_optimizer import get_active_prompt
from monitor import register_base_prompt
from security import sandbox
from monitoring.tracing import span

# Singleton agents — reuse across tasks
_reasoning  = ReasoningAgent()
_planner    = PlanningAgent()
_executor   = ExecutionAgent()
_evaluator  = EvaluatorAgent()
_memory_agent = MemoryAgent()

# Register base prompts with the monitor for optimization reference
register_base_prompt("reasoning", _reasoning.system_prompt)
register_base_prompt("planning",  _planner.system_prompt)
register_base_prompt("evaluator", _evaluator.system_prompt)


def _clip(text: str, n: int = 220) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"


async def _maybe_fix_and_run_generated_code(
    task_id: str,
    goal_type: str,
    execution: ExecutionOutput,
    context: dict,
    *,
    max_files: int = 1,
) -> dict:
    """
    For developer flows (goal_type build/code), detect generated .py files from filesystem writes,
    run them, and auto-fix errors (max 5 attempts) until they work.
    """
    gt = (goal_type or "").strip().lower()
    if gt not in ("code", "build"):
        return {"did_run": False}

    # Heuristic: look for filesystem.write_file outputs with a .py path.
    paths: list[str] = []
    try:
        for step_id in sorted((execution.raw_outputs or {}).keys()):
            out = execution.raw_outputs.get(step_id)
            if isinstance(out, dict) and isinstance(out.get("path"), str):
                p = out["path"]
                if p.endswith(".py"):
                    paths.append(p)
    except Exception:
        paths = []

    if not paths:
        return {"did_run": False}

    from tools import filesystem as fs_tool
    from agents.auto_fixer import AutoFixer

    ran: list[dict] = []
    fixer = AutoFixer()
    for file_path in paths[: max(1, int(max_files))]:
        try:
            code = await fs_tool.execute("read_file", {"path": file_path})
        except Exception as e:
            ran.append({"file_path": file_path, "success": False, "error": str(e), "attempts": 0})
            continue

        await store.log(task_id, f"✅ Code generated → running: {file_path}", "info")
        await store.push_stream_event(
            task_id,
            "agent_start",
            {"agent": "auto_fixer", "file_path": file_path},
        )
        res = await fixer.fix_and_run(code=code, file_path=file_path)
        await store.push_stream_event(
            task_id,
            "agent_done",
            {
                "agent": "auto_fixer",
                "file_path": file_path,
                "success": bool(res.get("success")),
                "attempts": int(res.get("attempts") or 0),
            },
        )
        if res.get("success"):
            fixed_n = max(int(res.get("attempts") or 1) - 1, 0)
            await store.log(
                task_id,
                f"✅ Code generated → Running → Fixed {fixed_n} error(s) → Working!",
                "info",
                {"file_path": file_path, "attempts": res.get("attempts"), "stdout": _clip(str(res.get('output') or ''), 400)},
            )

            # Optional: if this was inside a pulled GitHub repo, push a single-file update via API.
            try:
                gh_repo = (context or {}).get("github_repo")
                if gh_repo and (settings.github_token or "").strip():
                    root = Path("/tmp/pantheon_v2").resolve() / str(gh_repo).split("/")[-1]
                    fp = Path(str(res.get("file_path") or file_path)).resolve()
                    if root in fp.parents:
                        rel = str(fp.relative_to(root))
                        from agents.github_agent import GitHubAgent

                        await GitHubAgent().write_file(
                            gh_repo,
                            rel,
                            str(res.get("final_code") or ""),
                            commit_message=f"Auto-fix: {task_id[:8]}",
                        )
                        await store.log(task_id, f"Pushed fix to GitHub file {rel}", "info")
            except Exception as e:
                await store.log(task_id, f"GitHub push warning: {e}", "warning")
        else:
            await store.log(
                task_id,
                f"Auto-fix failed after {res.get('attempts')} attempt(s)",
                "warning",
                {"file_path": file_path, "error": _clip(str(res.get('last_error') or ''), 400)},
            )
        ran.append(res)

    return {"did_run": True, "results": ran}


def _extract_github_repo(text: str) -> str | None:
    """
    Extract owner/repo from a GitHub URL if present.
    """
    if not text:
        return None
    m = re.search(r"github\\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


async def run(
    task_id: str,
    command: str,
    context: dict,
    dry_run: bool,
) -> None:
    """
    Full autonomous execution loop.
    Updates the task record in DB at each phase transition.
    """
    context = dict(context or {})
    uid0 = context.get("user_id")
    lang = context.get("language")
    if not lang and uid0:
        u0 = await store.get_user_by_id(uid0)
        if u0 and u0.get("language"):
            lang = u0["language"]
    if not lang:
        lang = settings.default_language
    if lang not in settings.supported_languages:
        lang = settings.default_language
    context["language"] = lang

    ws_tok = sandbox.set_user_workspace(context.get("user_id"))
    prior_attempts: list[str] = []
    last_plan: Optional[PlanningOutput] = None
    last_execution: Optional[ExecutionOutput] = None
    last_evaluation: Optional[EvaluatorOutput] = None
    from memory.semantic_store import SemanticMemory

    sm = SemanticMemory(settings.db_path)

    try:
        # Optional: pre-pull a GitHub repo if command references one (developer flow).
        try:
            repo = _extract_github_repo(command)
            if repo:
                context["github_repo"] = repo
                from agents.github_agent import GitHubAgent

                await store.log(task_id, f"GitHub repo detected: {repo} — pulling…", "info")
                local = f"/tmp/pantheon_v2/{repo.split('/')[-1]}"
                await GitHubAgent().pull_repo(repo, local)
                context["github_local_path"] = local
        except Exception as e:
            await store.log(task_id, f"GitHub pull warning: {e}", "warning")

        with span("orchestrator.run", {"task_id": task_id, "command": command[:50]}):
            pass
        for iteration in range(1, settings.max_loop_iterations + 1):
            await store.push_stream_event(
                task_id,
                "loop_start",
                {"iteration": iteration, "max": settings.max_loop_iterations},
            )
            await store.log(task_id, f"=== Loop iteration {iteration}/{settings.max_loop_iterations} ===", "info")

            # ── 1. REASONING ──────────────────────────────────────────────
            await store.update_status(task_id, TaskStatus.REASONING)

            await store.push_stream_event(task_id, "agent_start", {"agent": "reasoning"})

            try:
                memories = await sm.recall(command, limit=3)
                if memories:
                    context = dict(context)
                    context["relevant_memories"] = memories
            except Exception:
                pass

            # Pull relevant learnings from memory
            # (goal_type unknown yet — use "general" for first recall)
            prior_goal_type = "general"
            if last_evaluation:
                prior_goal_type = last_evaluation.summary[:20]  # rough proxy
            memory_snippets = await recall_relevant(prior_goal_type, limit=4)

            with span("agent.reasoning", {"task_id": task_id}):
                reasoning = await _reasoning.run(
                    ReasoningInput(
                        raw_goal=command,
                        context=context,
                        prior_attempts=prior_attempts,
                        memory_snippets=memory_snippets,
                    )
                )

            await store.push_stream_event(
                task_id,
                "agent_done",
                {
                    "agent": "reasoning",
                    "summary": _clip(reasoning.understood_goal),
                    "goal_type": reasoning.goal_type,
                    "complexity": reasoning.complexity,
                },
            )

            await store.log(task_id, f"Understood goal: {reasoning.understood_goal}", "info",
                            {"complexity": reasoning.complexity, "type": reasoning.goal_type})

            # Phase 4: Confidence check on reasoning
            confidence = score_reasoning(command, reasoning.model_dump())
            await store.log(
                task_id,
                f"Reasoning confidence: {confidence.score:.2f} ({confidence.level})",
                "warning" if confidence.level == "low" else "info",
                {"flags": confidence.flags},
            )
            if confidence.level == "low" and iteration == 1:
                await store.push_stream_event(
                    task_id,
                    "loop_done",
                    {"iteration": iteration, "outcome": "retry_reasoning", "confidence": confidence.score},
                )
                prior_attempts.append(
                    f"Low reasoning confidence ({confidence.score:.2f}): {confidence.reasoning}"
                )
                continue  # re-reason with the confidence feedback

            # If agent says clarification needed and no prior attempts, pause
            if reasoning.clarifications_needed and iteration == 1:
                await store.log(task_id, f"Clarification needed: {reasoning.clarifications_needed}", "warning")

            # ── 2. PLANNING ──────────────────────────────────────────────
            await store.update_status(task_id, TaskStatus.PLANNING)

            await store.push_stream_event(task_id, "agent_start", {"agent": "planning"})

            # Fetch goal-type-specific learnings for planner
            plan_snippets = await recall_relevant(reasoning.goal_type, limit=4)

            # Phase 4: Use optimized prompt if available for this goal type
            optimized_prompt = await get_active_prompt("planning", reasoning.goal_type)
            if optimized_prompt:
                _planner.system_prompt = optimized_prompt
                await store.log(task_id, f"Using optimized planner prompt for '{reasoning.goal_type}'", "info")
            else:
                from agents.planner import SYSTEM as _planner_default_system
                _planner.system_prompt = _planner_default_system

            with span("agent.planning", {"task_id": task_id}):
                plan = await _planner.run(
                    PlanningInput(
                        reasoning=reasoning,
                        memory_snippets=plan_snippets,
                        language=context.get("language", settings.default_language),
                    )
                )

            await store.push_stream_event(
                task_id,
                "agent_done",
                {
                    "agent": "planning",
                    "summary": _clip(plan.goal_summary),
                    "steps": len(plan.steps),
                },
            )

            # Phase 4: Confidence check on plan
            plan_confidence = score_plan(reasoning.understood_goal, plan.model_dump())
            await store.log(
                task_id,
                f"Plan confidence: {plan_confidence.score:.2f} ({plan_confidence.level})",
                "warning" if plan_confidence.level == "low" else "info",
                {"flags": plan_confidence.flags},
            )
            last_plan = plan

            await store.log(task_id, f"Plan: {len(plan.steps)} steps — {plan.goal_summary}", "info")
            await store.update_plan(task_id, plan.model_dump_json(), reasoning.goal_type,
                                    reasoning.understood_goal)

            if dry_run or not plan.steps:
                summary = "Dry run — plan generated, not executed." if dry_run else plan.notes
                await store.update_status(
                    task_id, TaskStatus.DONE,
                    summary=summary, eval_score=None, iterations=iteration
                )
                await store.push_stream_event(
                    task_id,
                    "loop_done",
                    {"iteration": iteration, "outcome": "dry_run" if dry_run else "empty_plan"},
                )
                return

            # ── 3. EXECUTION ─────────────────────────────────────────────
            await store.update_status(task_id, TaskStatus.EXECUTING)

            await store.push_stream_event(
                task_id,
                "agent_start",
                {"agent": "execution", "steps": len(plan.steps)},
            )
            with span("agent.execution", {"task_id": task_id, "step_count": len(plan.steps)}):
                execution = await _executor.run(
                    ExecutionInput(task_id=task_id, plan=plan)
                )
            last_execution = execution

            await store.push_stream_event(
                task_id,
                "agent_done",
                {
                    "agent": "execution",
                    "summary": f"{execution.succeeded}/{execution.steps_run} steps succeeded, {execution.failed} failed",
                    "succeeded": execution.succeeded,
                    "failed": execution.failed,
                },
            )

            await store.log(
                task_id,
                f"Execution: {execution.succeeded}/{execution.steps_run} succeeded, "
                f"{execution.failed} failed",
                "info" if execution.failed == 0 else "warning",
            )

            # ── Developer power: run generated code + auto-fix ───────────
            try:
                await _maybe_fix_and_run_generated_code(
                    task_id, reasoning.goal_type, execution, context
                )
            except Exception as e:
                await store.log(task_id, f"AutoFixer warning: {e}", "warning")

            # ── 4. EVALUATION ────────────────────────────────────────────
            await store.update_status(task_id, TaskStatus.EVALUATING)

            await store.push_stream_event(task_id, "agent_start", {"agent": "evaluator"})
            evaluation = await _evaluator.run(
                EvaluatorInput(
                    goal=reasoning.understood_goal,
                    success_criteria=reasoning.success_criteria,
                    plan=plan,
                    execution=execution,
                    task_id=task_id,
                )
            )
            with span("agent.evaluation", {"task_id": task_id, "score": evaluation.score}):
                pass
            last_evaluation = evaluation

            await store.push_stream_event(
                task_id,
                "agent_done",
                {
                    "agent": "evaluator",
                    "summary": _clip(evaluation.summary),
                    "score": evaluation.score,
                    "goal_met": evaluation.goal_met,
                },
            )

            await store.log(
                task_id,
                f"Evaluation: score={evaluation.score:.2f} goal_met={evaluation.goal_met}",
                "info" if evaluation.goal_met else "warning",
                {"summary": evaluation.summary},
            )

            # ── 5. MEMORY ────────────────────────────────────────────────
            await store.push_stream_event(task_id, "agent_start", {"agent": "memory"})
            mem_out = await _memory_agent.run(
                MemoryInput(
                    task_id=task_id,
                    goal=reasoning.understood_goal,
                    goal_type=reasoning.goal_type,
                    plan=plan,
                    execution=execution,
                    evaluation=evaluation,
                )
            )
            await store.push_stream_event(
                task_id,
                "agent_done",
                {
                    "agent": "memory",
                    "summary": _clip(mem_out.learning or ("stored" if mem_out.stored else "skipped")),
                    "stored": mem_out.stored,
                },
            )

            try:
                tags = list(reasoning.success_criteria or [])[:3]
                uid_mem = context.get("user_id")
                summary = evaluation.summary or ""
                await sm.store_memory(
                    task_id=task_id,
                    content=f"Goal: {reasoning.understood_goal}\nResult: {summary}",
                    memory_type=reasoning.goal_type,
                    tags=[str(t) for t in tags],
                    importance=float(evaluation.score),
                    owner_user_id=uid_mem,
                )
            except Exception:
                pass

            if evaluation.goal_met:
                try:
                    from agents.suggester import SuggesterAgent

                    suggestions_list = await SuggesterAgent().run(
                        reasoning.understood_goal,
                        evaluation.summary,
                        reasoning.goal_type,
                    )
                    if suggestions_list:
                        await store.save_suggestions(task_id, suggestions_list)
                        await store.log(
                            task_id,
                            f"Suggestions: {suggestions_list}",
                            "info",
                        )
                except Exception:
                    pass

            # ── 6. DECIDE: DONE or LOOP? ─────────────────────────────────
            results_json = json.dumps(
                [r.model_dump() for r in execution.results], default=str
            )

            if evaluation.goal_met:
                await store.update_status(
                    task_id, TaskStatus.DONE,
                    summary=evaluation.summary,
                    eval_score=evaluation.score,
                    iterations=iteration,
                    results_json=results_json,
                )
                await store.push_stream_event(
                    task_id,
                    "loop_done",
                    {
                        "iteration": iteration,
                        "outcome": "success",
                        "score": evaluation.score,
                    },
                )
                await store.log(task_id, f"DONE after {iteration} iteration(s). Score: {evaluation.score:.2f}", "info")
                return

            # Not done — prepare feedback for next loop iteration
            hint_summary = "; ".join(evaluation.improvement_hints[:3])
            await store.push_stream_event(
                task_id,
                "loop_done",
                {
                    "iteration": iteration,
                    "outcome": "retry_eval",
                    "score": evaluation.score,
                },
            )
            prior_attempts.append(
                f"Iteration {iteration}: score={evaluation.score:.2f}. "
                f"Failed: {evaluation.what_failed}. Hints: {hint_summary}"
            )
            await store.log(task_id, f"Looping — hints: {hint_summary}", "warning")

        # ── Max iterations reached ────────────────────────────────────────
        final_score = last_evaluation.score if last_evaluation else 0.0
        final_summary = (
            last_evaluation.summary if last_evaluation
            else "Max loop iterations reached without completion."
        )
        results_json = json.dumps(
            [r.model_dump() for r in (last_execution.results if last_execution else [])],
            default=str,
        )
        await store.update_status(
            task_id, TaskStatus.FAILED,
            summary=f"Max iterations reached. {final_summary}",
            eval_score=final_score,
            iterations=settings.max_loop_iterations,
            results_json=results_json,
            error="Did not meet success criteria within iteration limit.",
        )
        await store.push_stream_event(
            task_id,
            "loop_done",
            {
                "iteration": settings.max_loop_iterations,
                "outcome": "max_iterations",
                "score": final_score,
            },
        )

    except Exception as e:
        try:
            from monitoring.error_tracker import track_error

            await track_error(
                e,
                context={"phase": "orchestrator"},
                task_id=task_id,
                user_id=str(uid0 or context.get("user_id") or ""),
            )
        except Exception:
            pass
        import traceback
        tb = traceback.format_exc()
        await store.log(task_id, f"Fatal orchestrator error: {e}\n{tb}", "error")
        await store.update_status(
            task_id, TaskStatus.FAILED,
            summary=f"Fatal error: {e}",
            error=str(e),
            iterations=0,
        )
        await store.push_stream_event(
            task_id,
            "loop_done",
            {"iteration": 0, "outcome": "fatal", "error": str(e)[:200]},
        )
    finally:
        try:
            await _finalize_outbound(task_id, context)
        except Exception:
            pass
        sandbox.reset_user_workspace(ws_tok)


async def _finalize_outbound(task_id: str, context: dict) -> None:
    await _notify_telegram_if_needed(task_id, context)
    row = await store.get_task(task_id)
    if not row:
        return
    uid = row.get("user_id") or context.get("user_id") or ""
    st = row.get("status")
    if st == "done" and uid:
        try:
            from memory.redis_client import cache_delete_prefix

            await cache_delete_prefix(f"report:{uid}:")
        except Exception:
            pass
    try:
        import analytics as analytics_mod

        if st == "done":
            await analytics_mod.track(
                "task_completed",
                uid,
                goal_type=row.get("goal_type") or "",
                score=row.get("eval_score"),
                iterations=row.get("loop_iterations"),
            )
        elif st == "failed":
            await analytics_mod.track(
                "task_failed",
                uid,
                goal_type=row.get("goal_type") or "",
                error=(row.get("error") or row.get("summary") or "")[:200],
            )
    except Exception:
        pass
    try:
        if uid and st in ("done", "failed"):
            from webhook_sender import fire_webhook

            ev = "task.completed" if st == "done" else "task.failed"
            payload = {
                "task_id": task_id,
                "goal": row.get("goal") or row.get("command"),
                "status": st,
                "eval_score": row.get("eval_score"),
                "summary": row.get("summary"),
            }
            asyncio.create_task(fire_webhook(uid, ev, payload))
    except Exception:
        pass


async def _notify_telegram_if_needed(task_id: str, context: dict) -> None:
    chat_id = context.get("telegram_chat_id")
    if not chat_id:
        return
    from notifications import send_telegram

    row = await store.get_task(task_id)
    if not row:
        return
    st = row.get("status")
    goal = (row.get("goal") or row.get("command") or "") or ""
    if st == "done":
        score = row.get("eval_score")
        score_s = f"{float(score):.2f}" if score is not None else "0.00"
        summary = (row.get("summary") or "")[:200]
        text = f"✅ {goal[:80]}\nScore: {score_s}\n{summary[:200]}"
        await send_telegram(str(chat_id), text)
    elif st == "failed":
        err = (row.get("error") or row.get("summary") or "")[:100]
        text = f"❌ Failed: {goal[:60]}\n{err}"
        await send_telegram(str(chat_id), text)
