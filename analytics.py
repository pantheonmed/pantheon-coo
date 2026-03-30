"""
analytics.py — product analytics events (writes to memory/store).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import memory.store as store
from memory.db_pool import get_pool

EVENTS = [
    "user_registered",
    "user_logged_in",
    "task_submitted",
    "task_completed",
    "task_failed",
    "plan_upgraded",
    "template_used",
    "tool_used",
]


async def track(event_type: str, user_id: str = "", **properties: Any) -> None:
    await store.track_event(event_type, user_id, dict(properties))


def _period_hours(period: str) -> int:
    return {"7d": 168, "30d": 720, "90d": 2160}.get(period, 168)


async def build_admin_report(period: str) -> dict[str, Any]:
    """Aggregate analytics for GET /admin/analytics."""
    hours = _period_hours(period)
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since,)
        ) as cur:
            new_users = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT COUNT(DISTINCT user_id) FROM tasks
               WHERE user_id IS NOT NULL AND user_id != '' AND created_at >= ?""",
            (since,),
        ) as cur:
            active_users = int((await cur.fetchone())[0])

        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (since,)
        ) as cur:
            total_tasks = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT COUNT(*) FROM tasks WHERE status='done' AND created_at >= ?""",
            (since,),
        ) as cur:
            done_n = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT COUNT(*) FROM tasks WHERE status='failed' AND created_at >= ?""",
            (since,),
        ) as cur:
            fail_n = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT AVG(eval_score) FROM tasks WHERE status='done' AND eval_score IS NOT NULL
               AND created_at >= ?""",
            (since,),
        ) as cur:
            row = await cur.fetchone()
            avg_score = float(row[0]) if row and row[0] is not None else 0.0

        async with db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM orders
               WHERE status IN ('paid','captured','completed') AND created_at >= ?""",
            (since,),
        ) as cur:
            revenue_paise = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT goal_type, COUNT(*) as c FROM tasks
               WHERE created_at >= ? AND goal_type != '' GROUP BY goal_type ORDER BY c DESC LIMIT 10""",
            (since,),
        ) as cur:
            top_goal_types = [{"type": r[0], "count": r[1]} for r in await cur.fetchall()]

        async with db.execute(
            """SELECT properties FROM analytics_events
               WHERE event_type='template_used' AND created_at >= ?""",
            (since,),
        ) as cur:
            tmpl_counts: dict[str, int] = {}
            for (props,) in await cur.fetchall():
                try:
                    d = json.loads(props or "{}")
                    tid = d.get("template_id") or "unknown"
                    tmpl_counts[tid] = tmpl_counts.get(tid, 0) + 1
                except Exception:
                    pass
            top_templates = [
                {"id": k, "uses": v}
                for k, v in sorted(tmpl_counts.items(), key=lambda x: -x[1])[:10]
            ]

        async with db.execute(
            """SELECT DATE(created_at) as d, COUNT(*) as c,
                      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as okc
               FROM tasks WHERE created_at >= ?
               GROUP BY DATE(created_at) ORDER BY d""",
            (since,),
        ) as cur:
            daily_tasks = []
            for r in await cur.fetchall():
                d, c, okc = r[0], r[1], r[2] or 0
                sr = (okc / c) if c else 0.0
                daily_tasks.append({"date": d, "count": c, "success_rate": round(sr, 4)})

        async with db.execute(
            """
            SELECT u.user_id, u.email,
              CAST((
                julianday('now') - julianday(
                  COALESCE(
                    (SELECT MAX(created_at) FROM tasks t WHERE t.user_id = u.user_id),
                    u.created_at
                  )
                )
              ) AS INTEGER) AS days_inactive
            FROM users u
            WHERE EXISTS (SELECT 1 FROM tasks t WHERE t.user_id = u.user_id)
              AND (
                julianday('now') - julianday(
                  (SELECT MAX(created_at) FROM tasks t WHERE t.user_id = u.user_id)
                )
              ) >= 7
            LIMIT 50
            """,
        ) as cur:
            churn_risk_users = [
                {"user_id": r[0], "email": r[1], "days_inactive": int(r[2] or 0)}
                for r in await cur.fetchall()
            ]

        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (today_start,),
        ) as cur:
            tasks_today = int((await cur.fetchone())[0])

    denom = done_n + fail_n
    success_rate = (done_n / denom) if denom else 0.0

    return {
        "period": period,
        "new_users": new_users,
        "active_users": active_users,
        "tasks_today": tasks_today,
        "total_tasks": total_tasks,
        "success_rate": round(success_rate, 4),
        "avg_score": round(avg_score, 4),
        "revenue_inr": round(revenue_paise / 100.0, 2),
        "top_goal_types": top_goal_types,
        "top_templates": top_templates,
        "daily_tasks": daily_tasks,
        "churn_risk_users": churn_risk_users[:20],
    }


async def export_events_csv_for_period(period: str) -> str:
    hours = _period_hours(period)
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    return await export_events_csv(since)


async def export_events_csv(since_iso: str) -> str:
    """CSV of analytics_events since timestamp."""
    lines = ["id,event_type,user_id,properties,created_at"]
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT id, event_type, user_id, properties, created_at FROM analytics_events WHERE created_at >= ? ORDER BY id",
            (since_iso,),
        ) as cur:
            async for row in cur:
                rid, et, uid, props, ca = row[0], row[1], row[2], row[3], row[4]
                props_esc = (props or "").replace('"', '""')
                lines.append(f'{rid},{et},{uid},"{props_esc}",{ca}')
    return "\n".join(lines)
