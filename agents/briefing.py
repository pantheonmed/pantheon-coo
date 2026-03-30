"""
agents/briefing.py
───────────────────
Phase 5 — Daily Briefing Agent

Every day (or on demand), the COO generates a structured briefing:
  - What was accomplished (tasks completed, eval scores)
  - What failed and why
  - Active projects and their progress
  - Institutional memory growth (learnings, custom tools built)
  - System health (model router status, avg scores)
  - Recommendations for the next 24 hours

The briefing is:
  - Stored in the DB for the dashboard
  - Emailed to configured recipients
  - Sent as a WhatsApp summary to configured numbers

This is the COO "reporting to the CEO" — closing the loop on autonomous operation.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

from agents.model_router import call_model
from models import BriefingReport, BriefingSection
from config import settings

BRIEFING_SYSTEM = """
You are the Chief Operating Officer of Pantheon, generating a daily operational briefing.

Write like a real COO reporting to a CEO: direct, data-driven, no fluff.
Surface the most important things. Flag anything that needs attention.

You will receive raw operational data. Transform it into a structured report.

Output JSON:
{
  "headline": "one sentence executive summary",
  "health": "good|degraded|critical",
  "sections": [
    {
      "title": "section title",
      "content": "2-4 sentences of analysis, not just data recitation",
      "status": "info|warning|critical"
    }
  ],
  "recommendations": [
    "specific, actionable recommendation 1",
    "specific, actionable recommendation 2"
  ],
  "full_text": "full plain-text version suitable for email/WhatsApp (200-400 words)"
}

Sections to include (in order):
1. Execution summary (tasks run, success rate, notable completions)
2. Failures & issues (what went wrong, pattern analysis)
3. System intelligence (learnings added, custom tools built, prompt optimizations)
4. Active projects (progress update)
5. System health (model router, avg eval score, loop iterations)
6. 24-hour outlook (what's scheduled, what to watch)
"""


async def generate_briefing(
    metrics: dict,
    projects: list[dict],
    recent_tasks: list[dict],
    recent_learnings: list[str],
) -> BriefingReport:
    """Generate a full COO briefing from operational data."""

    # Build data payload for the agent
    data = {
        "period": f"Last {metrics.get('period_hours', 24)} hours",
        "task_metrics": metrics.get("totals", {}),
        "performance": metrics.get("performance", {}),
        "by_goal_type": metrics.get("by_goal_type", [])[:5],
        "alerts": metrics.get("alerts", []),
        "health": metrics.get("health", "unknown"),
        "model_status": metrics.get("model", {}),
        "institutional_memory": metrics.get("institutional_memory", {}),
        "active_projects": [
            {
                "name": p.get("name"),
                "progress": f"{p.get('progress', 0):.0%}",
                "status": p.get("status"),
            }
            for p in projects[:5]
        ],
        "recent_tasks_sample": [
            {
                "goal": t.get("goal", "")[:80],
                "status": t.get("status"),
                "score": t.get("eval_score"),
            }
            for t in recent_tasks[:8]
        ],
        "recent_learnings": recent_learnings[:5],
    }

    user_msg = (
        f"Operational data for briefing:\n{json.dumps(data, indent=2, default=str)}\n\n"
        "Generate the COO briefing JSON now."
    )

    try:
        response = call_model(
            BRIEFING_SYSTEM,
            user_msg,
            use_fast=False,
            max_tokens=2000,
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:raw.rfind("```")]

        data_out = json.loads(raw)

        sections = [
            BriefingSection(
                title=s.get("title", ""),
                content=s.get("content", ""),
                status=s.get("status", "info"),
            )
            for s in data_out.get("sections", [])
        ]

        return BriefingReport(
            period_hours=metrics.get("period_hours", 24),
            headline=data_out.get("headline", ""),
            health=data_out.get("health", "unknown"),
            sections=sections,
            metrics_snapshot=metrics,
            recommendations=data_out.get("recommendations", []),
            full_text=data_out.get("full_text", ""),
        )

    except Exception as e:
        # Fallback: mechanical briefing if agent fails
        totals = metrics.get("totals", {})
        perf = metrics.get("performance", {})
        return BriefingReport(
            period_hours=metrics.get("period_hours", 24),
            headline=f"COO Briefing: {totals.get('tasks', 0)} tasks, "
                     f"{perf.get('success_rate', 0):.0%} success rate",
            health=metrics.get("health", "unknown"),
            sections=[
                BriefingSection(
                    title="Execution summary",
                    content=(
                        f"{totals.get('tasks', 0)} tasks processed. "
                        f"{totals.get('done', 0)} completed, "
                        f"{totals.get('failed', 0)} failed. "
                        f"Avg eval score: {perf.get('avg_eval_score', 0):.2f}."
                    ),
                    status="info" if not metrics.get("alerts") else "warning",
                )
            ],
            recommendations=["Review failed tasks and retry if needed."],
            full_text=f"Briefing generation encountered an error: {e}",
        )


async def send_briefing(
    report: BriefingReport,
    email_recipients: list[str],
    whatsapp_numbers: list[str],
) -> dict:
    """Distribute the briefing via email and/or WhatsApp."""
    sent = {"email": [], "whatsapp": []}

    # Email
    for addr in email_recipients:
        try:
            from tools.email import execute as email_execute
            await email_execute("send_report", {
                "to": addr,
                "task_id": f"briefing-{datetime.utcnow().strftime('%Y%m%d')}",
                "goal": f"Daily COO Briefing — {datetime.utcnow().strftime('%Y-%m-%d')}",
                "summary": report.headline,
                "results": [],
                "eval_score": None,
            })
            sent["email"].append(addr)
        except Exception as e:
            print(f"[Briefing] Email to {addr} failed: {e}")

    # WhatsApp
    for number in whatsapp_numbers:
        try:
            from whatsapp import send as wa_send
            # Truncate to WhatsApp limit
            msg = (
                f"📊 *COO Daily Briefing*\n\n"
                f"{report.headline}\n\n"
                f"{report.full_text[:600]}...\n\n"
                f"Health: {report.health.upper()}"
            )
            await wa_send(number, msg)
            sent["whatsapp"].append(number)
        except Exception as e:
            print(f"[Briefing] WhatsApp to {number} failed: {e}")

    return sent
