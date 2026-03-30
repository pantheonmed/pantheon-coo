"""
performance_report.py
─────────────────────
Structured GET /report payload: aggregates + cached Claude recommendation.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import aiosqlite

from config import settings
from agents.model_router import call_model, get_model_usage_counts

PERIOD_HOURS = {"24h": 24, "7d": 168, "30d": 720}

_REC_CACHE: dict[str, tuple[float, str]] = {}
_REC_TTL_SEC = 300.0


def _normalize_period(period: str | None) -> str:
    if not period:
        return "24h"
    p = period.strip().lower()
    if p in PERIOD_HOURS:
        return p
    return "24h"


def _tool_counts_from_plans(plan_rows: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pj in plan_rows:
        if not pj or pj == "{}":
            continue
        try:
            plan = json.loads(pj)
            for step in plan.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                t = step.get("tool")
                if not t:
                    continue
                ts = t if isinstance(t, str) else getattr(t, "value", str(t))
                counts[ts] = counts.get(ts, 0) + 1
        except Exception:
            continue
    return counts


def _fallback_recommendation() -> str:
    return (
        "Focus on the lowest-scoring goal types and reduce failed runs by tightening "
        "success criteria before execution."
    )


def _make_recommendation(stats_without_rec: dict[str, Any]) -> str:
    cache_key = hashlib.sha256(
        json.dumps(stats_without_rec, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    now = time.time()
    ck = f"{stats_without_rec.get('period')}:{cache_key}"
    if ck in _REC_CACHE and now - _REC_CACHE[ck][0] < _REC_TTL_SEC:
        return _REC_CACHE[ck][1]
    try:
        r = call_model(
            "You reply with exactly one short sentence. No markdown, no quotes.",
            "Given this Pantheon COO performance summary (JSON), name one specific actionable "
            "improvement for the next sprint:\n"
            + json.dumps(stats_without_rec, indent=2, default=str)[:4500],
            use_fast=True,
            max_tokens=120,
        )
        text = (r.text or "").strip().split("\n")[0].strip()
        if not text:
            text = _fallback_recommendation()
    except Exception:
        text = _fallback_recommendation()
    _REC_CACHE[ck] = (now, text)
    return text


async def build_performance_report(period: str | None) -> dict[str, Any]:
    pkey = _normalize_period(period)
    hours = PERIOD_HOURS[pkey]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT
                COUNT(*) as total,
                AVG(eval_score) as avg_score,
                AVG(loop_iterations) as avg_iters,
                SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done_n,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed_n
               FROM tasks WHERE created_at >= ?""",
            (cutoff,),
        ) as cur:
            row = await cur.fetchone()
            overall = dict(row) if row else {}

        async with db.execute(
            """SELECT goal_type, COUNT(*) as cnt, AVG(eval_score) as avg_score
               FROM tasks
               WHERE created_at >= ? AND goal_type != '' AND goal_type IS NOT NULL
               GROUP BY goal_type
               ORDER BY cnt DESC
               LIMIT 8""",
            (cutoff,),
        ) as cur:
            goal_rows = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT plan_json FROM tasks WHERE created_at >= ?",
            (cutoff,),
        ) as cur:
            plans = [r[0] for r in await cur.fetchall()]

        async with db.execute(
            "SELECT COUNT(*) FROM custom_tools WHERE created_at >= ?",
            (cutoff,),
        ) as cur:
            custom_built = (await cur.fetchone())[0]

        async with db.execute(
            "SELECT COALESCE(SUM(usage_count), 0) FROM custom_tools",
        ) as cur:
            total_uses = (await cur.fetchone())[0] or 0

        async with db.execute(
            "SELECT COUNT(*) FROM learnings WHERE created_at >= ?",
            (cutoff,),
        ) as cur:
            learnings_n = (await cur.fetchone())[0]

    total = int(overall.get("total") or 0)
    done_n = int(overall.get("done_n") or 0)
    avg_score = float(overall.get("avg_score") or 0.0)
    avg_iters = float(overall.get("avg_iters") or 0.0)
    success_rate = (done_n / total) if total else 0.0

    top_goal_types = []
    for g in goal_rows:
        top_goal_types.append(
            {
                "type": g.get("goal_type") or "",
                "count": int(g.get("cnt") or 0),
                "avg_score": round(float(g["avg_score"]), 3) if g.get("avg_score") is not None else 0.0,
            }
        )

    tc = _tool_counts_from_plans(plans)
    most_used_tools = sorted(
        [{"tool": k, "count": v} for k, v in tc.items()],
        key=lambda x: -x["count"],
    )[:12]

    worst_goal_type = ""
    if goal_rows:
        scored = [g for g in goal_rows if g.get("avg_score") is not None]
        if scored:
            worst = min(scored, key=lambda x: float(x["avg_score"] or 0.0))
            worst_goal_type = str(worst.get("goal_type") or "")

    tokens_saved_estimate = int(total_uses * 500)

    usage = get_model_usage_counts()

    base: dict[str, Any] = {
        "period": pkey,
        "total_tasks": total,
        "success_rate": round(success_rate, 4),
        "avg_eval_score": round(avg_score, 4),
        "avg_loop_iterations": round(avg_iters, 3),
        "top_goal_types": top_goal_types,
        "most_used_tools": most_used_tools,
        "custom_tools_built": int(custom_built),
        "learnings_added": int(learnings_n),
        "total_tokens_saved": tokens_saved_estimate,
        "model_usage": usage,
        "worst_goal_type": worst_goal_type,
    }

    rec = _make_recommendation({k: v for k, v in base.items() if k != "recommendation"})
    base["recommendation"] = rec
    return base
