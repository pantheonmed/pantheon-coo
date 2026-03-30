"""
monitor.py
───────────
Phase 4 — Performance Monitor

Runs every N seconds (configurable) and computes health metrics:
  - Average eval score (last 24h, last 7d, by goal type)
  - Failure rate
  - Average loop iterations (proxy for task difficulty/agent quality)
  - Agent-specific performance (which agent is the bottleneck?)
  - Model usage (Claude vs fallback)

When metrics fall below thresholds:
  → Fires an alert (logs + optional webhook)
  → Triggers PromptOptimizer for the underperforming agent
  → Updates the dashboard with health status

The monitor is the COO's immune system — it detects and responds to
degradation without human intervention.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiosqlite

from config import settings
from agents.prompt_optimizer import optimize_prompt, save_prompt, get_active_prompt
from agents.reasoning import ReasoningAgent
from agents.planner import PlanningAgent
from agents.evaluator import EvaluatorAgent

DB = settings.db_path

# Registry of base agent prompts for optimizer reference
_AGENT_PROMPTS: dict[str, str] = {}


def register_base_prompt(agent_name: str, prompt: str) -> None:
    _AGENT_PROMPTS[agent_name] = prompt


async def get_metrics(hours: int = 24) -> dict:
    """Compute COO performance metrics for the last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row

        # Overall stats
        async with db.execute(
            """SELECT
                COUNT(*) as total,
                AVG(eval_score) as avg_score,
                AVG(loop_iterations) as avg_iters,
                SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
               FROM tasks WHERE created_at >= ?""",
            (cutoff,),
        ) as cur:
            overall = dict(await cur.fetchone() or {})

        # By goal type
        async with db.execute(
            """SELECT goal_type,
                COUNT(*) as count,
                AVG(eval_score) as avg_score,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
               FROM tasks WHERE created_at >= ? AND goal_type != ''
               GROUP BY goal_type ORDER BY count DESC""",
            (cutoff,),
        ) as cur:
            by_type = [dict(r) for r in await cur.fetchall()]

        # Score trend (hourly buckets for last 24h)
        async with db.execute(
            """SELECT
                strftime('%Y-%m-%dT%H:00', created_at) as hour,
                AVG(eval_score) as avg_score,
                COUNT(*) as count
               FROM tasks
               WHERE created_at >= ? AND eval_score IS NOT NULL
               GROUP BY hour ORDER BY hour""",
            (cutoff,),
        ) as cur:
            trend = [dict(r) for r in await cur.fetchall()]

        # Learnings count
        async with db.execute("SELECT COUNT(*) as c FROM learnings") as cur:
            learnings = (await cur.fetchone())[0]

        # Custom tools count
        async with db.execute("SELECT COUNT(*) as c FROM custom_tools") as cur:
            custom_tools = (await cur.fetchone())[0]

    total = overall.get("total") or 0
    done = overall.get("done") or 0
    failed = overall.get("failed") or 0
    avg_score = overall.get("avg_score") or 0.0
    avg_iters = overall.get("avg_iters") or 0.0
    failure_rate = failed / max(total, 1)

    # Health assessment
    health = "good"
    alerts = []
    if avg_score < settings.alert_score_threshold and total >= 3:
        health = "degraded"
        alerts.append(f"Avg eval score {avg_score:.2f} below threshold {settings.alert_score_threshold}")
    if failure_rate > settings.alert_failure_rate and total >= 3:
        health = "degraded"
        alerts.append(f"Failure rate {failure_rate:.1%} above threshold {settings.alert_failure_rate:.0%}")
    if avg_iters > settings.max_loop_iterations * 0.8:
        health = "strained"
        alerts.append(f"High avg loop iterations: {avg_iters:.1f} (max={settings.max_loop_iterations})")

    if not (settings.anthropic_api_key or "").strip():
        alerts.append("API_KEY_INVALID: ANTHROPIC_API_KEY is empty")
    elif failure_rate > 0.5 and total >= 5:
        alerts.append("HIGH_FAILURE_RATE: over 50% tasks failed in window")

    from agents.model_router import router_status
    model_info = router_status()

    return {
        "period_hours": hours,
        "computed_at": datetime.utcnow().isoformat(),
        "health": health,
        "alerts": alerts,
        "totals": {
            "tasks": total,
            "done": done,
            "failed": failed,
            "failure_rate": round(failure_rate, 3),
        },
        "performance": {
            "avg_eval_score": round(avg_score, 3) if avg_score else None,
            "avg_loop_iterations": round(avg_iters, 2) if avg_iters else None,
            "success_rate": round(done / max(total, 1), 3),
        },
        "by_goal_type": by_type,
        "score_trend": trend,
        "institutional_memory": {
            "learnings": learnings,
            "custom_tools": custom_tools,
        },
        "model": model_info,
    }


async def monitor_loop() -> None:
    """Background loop that checks metrics and triggers optimization."""
    print("[Monitor] Performance monitor started.")
    await asyncio.sleep(60)  # warm-up: don't fire on first startup

    while True:
        try:
            await _check_and_respond()
        except Exception as e:
            print(f"[Monitor] Error: {e}")
        await asyncio.sleep(settings.monitor_interval_seconds)


async def _check_and_respond() -> None:
    metrics = await get_metrics(hours=24)
    health = metrics["health"]
    alerts = metrics["alerts"]

    if alerts:
        print(f"[Monitor] Health={health}. Alerts: {alerts}")

    # Check if any goal type needs prompt optimization
    for gt in metrics["by_goal_type"]:
        goal_type = gt.get("goal_type", "")
        count = gt.get("count", 0)
        avg_score = gt.get("avg_score") or 0.0
        failed = gt.get("failed", 0)

        # Only optimize if we have enough data and performance is poor
        if (count >= settings.prompt_optimize_after
                and avg_score < settings.alert_score_threshold
                and goal_type):
            await _try_optimize_agents(goal_type, avg_score)


async def _try_optimize_agents(goal_type: str, avg_score: float) -> None:
    """Attempt to optimize agent prompts for a specific goal type."""
    import memory.store as store

    # Get recent failed tasks of this type
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT goal, eval_score, results_json FROM tasks
               WHERE goal_type=? AND status='failed'
               ORDER BY created_at DESC LIMIT 6""",
            (goal_type,),
        ) as cur:
            failures = [dict(r) for r in await cur.fetchall()]

    if not failures:
        return

    # Collect improvement hints from evaluator outputs
    hints = []
    for f in failures:
        try:
            results = json.loads(f.get("results_json", "[]"))
            for r in results:
                if isinstance(r, dict) and r.get("error"):
                    hints.append(r["error"][:80])
        except Exception:
            pass

    # Optimize the planner prompt (most impactful)
    agent_name = "planning"
    base_prompt = _AGENT_PROMPTS.get(agent_name, "")
    if not base_prompt:
        return

    # Check existing version
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT MAX(version) as v FROM agent_prompts WHERE agent_name=? AND goal_type=?",
            (agent_name, goal_type),
        ) as cur:
            row = await cur.fetchone()
            current_version = row[0] or 0

    print(f"[Monitor] Optimizing '{agent_name}' prompt for goal_type='{goal_type}' (avg_score={avg_score:.2f})")

    result = await optimize_prompt(
        agent_name=agent_name,
        goal_type=goal_type,
        current_prompt=base_prompt,
        failure_examples=failures,
        improvement_hints=hints[:8],
    )

    if result:
        await save_prompt(
            agent_name=agent_name,
            goal_type=goal_type,
            prompt=result["new_prompt"],
            version=current_version + 1,
            notes=f"Auto-optimized. Changes: {result['changes_made'][:2]}",
        )
        print(
            f"[Monitor] New prompt v{current_version+1} saved for {agent_name}/{goal_type}. "
            f"Expected: {result.get('expected_improvement', '')}"
        )
