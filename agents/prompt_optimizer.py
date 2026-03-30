"""
agents/prompt_optimizer.py
───────────────────────────
Phase 4 — Autonomous Prompt Optimizer

When an agent consistently underperforms for a specific goal type
(low eval scores, repeated retries, common failure patterns),
the Prompt Optimizer rewrites that agent's system prompt.

How it works:
  1. PerformanceMonitor flags a (agent, goal_type) pair with low avg score
  2. PromptOptimizer is called with the current prompt + failure examples
  3. Claude rewrites the prompt to address the specific failure patterns
  4. New prompt is A/B tested: next N tasks of that type use the new prompt
  5. If score improves → keep. If not → revert.

This is the "COO improving its own team" — not just task execution,
but the intelligence of the system itself.

Prompts are stored in the DB with version history so we can always rollback.
"""
from __future__ import annotations
import json
import asyncio
import aiosqlite
from datetime import datetime
from typing import Optional

from agents.model_router import call_model
from config import settings

DB = settings.db_path

async def init_prompt_store() -> None:
    """Tables created by store.init() — no-op here."""
    pass


async def get_active_prompt(agent_name: str, goal_type: str) -> Optional[str]:
    """Return the active custom prompt for an agent+goal_type, or None (use default)."""
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT prompt_text FROM agent_prompts
               WHERE agent_name=? AND goal_type=? AND is_active=1
               ORDER BY version DESC LIMIT 1""",
            (agent_name, goal_type),
        ) as cur:
            row = await cur.fetchone()
            return row["prompt_text"] if row else None


async def save_prompt(
    agent_name: str, goal_type: str, prompt: str, version: int, notes: str = ""
) -> None:
    # Deactivate old prompts for this agent+type
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE agent_prompts SET is_active=0 WHERE agent_name=? AND goal_type=?",
            (agent_name, goal_type),
        )
        await db.execute(
            """INSERT INTO agent_prompts
               (agent_name, goal_type, prompt_text, version, is_active, created_at, notes)
               VALUES (?,?,?,?,1,?,?)""",
            (agent_name, goal_type, prompt, version,
             datetime.utcnow().isoformat(), notes),
        )
        await db.commit()


async def optimize_prompt(
    agent_name: str,
    goal_type: str,
    current_prompt: str,
    failure_examples: list[dict],
    improvement_hints: list[str],
) -> Optional[dict]:
    """
    Rewrite an agent's system prompt to fix observed failure patterns.
    Returns the optimization result dict or None on failure.
    """
    examples_str = ""
    for i, ex in enumerate(failure_examples[:4], 1):
        examples_str += f"\nExample {i}:\n"
        examples_str += f"  Goal: {ex.get('goal', '')[:100]}\n"
        examples_str += f"  Eval score: {ex.get('eval_score', 'unknown')}\n"
        failed = ex.get("what_failed", [])
        if failed:
            examples_str += f"  What failed: {failed[:2]}\n"

    hints_str = "\n".join(f"  - {h}" for h in improvement_hints[:5])

    user_msg = f"""Agent: {agent_name}
Goal type: {goal_type}

Current system prompt:
---
{current_prompt[:2000]}
---

Failure examples:{examples_str}

Recurring improvement hints from evaluator:
{hints_str}

Rewrite the system prompt to prevent these failures. Return JSON."""

    try:
        response = call_model(
            OPTIMIZER_SYSTEM,
            user_msg,
            use_fast=False,  # use full model for prompt optimization
            max_tokens=3000,
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:raw.rfind("```")]

        data = json.loads(raw)
        new_prompt = data.get("rewritten_prompt", "")
        if not new_prompt or len(new_prompt) < 100:
            return None

        return {
            "agent_name": agent_name,
            "goal_type": goal_type,
            "new_prompt": new_prompt,
            "changes_made": data.get("changes_made", []),
            "expected_improvement": data.get("expected_improvement", ""),
        }
    except Exception as e:
        print(f"[PromptOptimizer] Failed for {agent_name}/{goal_type}: {e}")
        return None


async def get_prompt_history(agent_name: str) -> list[dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT agent_name, goal_type, version, avg_score, task_count,
                      is_active, created_at, notes
               FROM agent_prompts WHERE agent_name=?
               ORDER BY created_at DESC LIMIT 20""",
            (agent_name,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
