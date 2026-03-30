"""
insights_engine.py — BI-style aggregates over task history (Task 88).

Kept as a top-level module because `analytics.py` is already a module in this repo.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import memory.store as store


class InsightsEngine:
    async def generate_weekly_insights(self, user_id: str) -> dict[str, Any]:
        since = (datetime.utcnow() - timedelta(days=7)).isoformat()
        async with store.get_pool().acquire() as db:
            async with db.execute(
                """SELECT command, status, eval_score, goal_type, created_at, completed_at
                   FROM tasks WHERE user_id=? AND created_at >= ?""",
                (user_id, since),
            ) as cur:
                rows = await cur.fetchall()
        done = [r for r in rows if r[1] == "done"]
        failed = [r for r in rows if r[1] == "failed"]
        hours = Counter()
        for r in done:
            try:
                ca = datetime.fromisoformat(r[5] or r[4])
                hours[ca.hour] += 1
            except Exception:
                continue
        best_hour = hours.most_common(1)[0][0] if hours else 0
        gt = Counter((r[3] or "unknown") for r in rows)
        success_rate = len(done) / max(len(rows), 1)
        return {
            "period_days": 7,
            "tasks_total": len(rows),
            "tasks_done": len(done),
            "tasks_failed": len(failed),
            "success_rate": round(success_rate, 4),
            "most_productive_hour_utc": best_hour,
            "goal_type_breakdown": dict(gt),
            "time_saved_hours_estimate": round(len(done) * 0.2, 2),
            "recommendations": [
                "Try scheduling recurring reports with /schedules",
                "Use templates for repeated supplier or CRM flows",
            ],
        }

    async def predict_task_success(
        self, command: str, goal_type: str
    ) -> dict[str, Any]:
        prefix = (command or "")[:40].lower()
        async with store.get_pool().acquire() as db:
            async with db.execute(
                """SELECT status, eval_score FROM tasks
                   WHERE lower(command) LIKE ? OR goal_type=? LIMIT 50""",
                (f"%{prefix}%", goal_type or ""),
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            return {
                "success_rate": 0.75,
                "est_seconds": 120,
                "similar_tasks": [],
            }
        ok = sum(1 for r in rows if r[0] == "done")
        scores = [float(r[1] or 0) for r in rows if r[1] is not None]
        return {
            "success_rate": round(ok / len(rows), 4),
            "est_seconds": 90 + len(rows) * 2,
            "similar_tasks": [{"hint": "historical match"}][:5],
            "avg_eval": round(sum(scores) / max(len(scores), 1), 3) if scores else 0.0,
        }

    async def find_automation_opportunities(self, user_id: str) -> list[dict[str, Any]]:
        async with store.get_pool().acquire() as db:
            async with db.execute(
                "SELECT command, COUNT(*) as c FROM tasks WHERE user_id=? GROUP BY command HAVING c >= 3",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            {
                "command": r[0],
                "count": int(r[1]),
                "suggestion": "Schedule this to run automatically",
            }
            for r in rows[:20]
        ]


_engine = InsightsEngine()


def get_insights_engine() -> InsightsEngine:
    return _engine
