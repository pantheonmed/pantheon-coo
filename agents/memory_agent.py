"""
agents/memory_agent.py
──────────────────────
Memory Agent — the COO's institutional knowledge layer.

After every completed task (success or failure), the Memory Agent:
  1. Distills a reusable "learning" from the execution
  2. Tags it by goal type for future recall
  3. Stores it in the memory database

Before a new task, the Orchestrator queries this agent's store
to inject relevant learnings into the Reasoning and Planning agents.

This is what makes the COO get smarter over time.
"""
import json
from agents.base import BaseAgent
from config import settings
from models import MemoryInput, MemoryOutput
import memory.store as store


SYSTEM = """
You are the Memory Agent of Pantheon COO OS.

Your role: distill a reusable learning from a completed task execution.

Given the goal, plan, results, and evaluation, write a SINGLE clear learning
that would help a future AI agent handle a similar task better.

Rules:
- Be specific, not generic ("Always create the directory before writing files" not "be careful")
- Focus on what was unexpected or what required correction
- Include tool-specific tips if relevant
- Max 2 sentences

OUTPUT: valid JSON only:
{
  "stored": true,
  "learning": "string — the distilled learning for future reference"
}
"""


class MemoryAgent(BaseAgent[MemoryInput, MemoryOutput]):
    name = "memory"
    system_prompt = SYSTEM
    model = settings.claude_model_fast
    max_tokens = 256

    async def run(self, inp: MemoryInput) -> MemoryOutput:
        msg = f"""Goal: {inp.goal}
Goal type: {inp.goal_type}
Steps run: {inp.execution.steps_run} (succeeded: {inp.execution.succeeded}, failed: {inp.execution.failed})
Eval score: {inp.evaluation.score}
What worked: {inp.evaluation.what_worked}
What failed: {inp.evaluation.what_failed}
Hints given: {inp.evaluation.improvement_hints}

Distill a learning and return the JSON."""

        output = await self._call_claude_async(msg, MemoryOutput)

        # Persist the learning to DB
        await store.save_learning(
            task_id=inp.task_id,
            goal_type=inp.goal_type,
            learning=output.learning,
            score=inp.evaluation.score,
        )

        return output


# ─────────────────────────────────────────────────────────────────────────────
# Recall helper — used by orchestrator before starting a task
# ─────────────────────────────────────────────────────────────────────────────

async def recall_relevant(goal_type: str, limit: int = 5) -> list[str]:
    """Return recent high-quality learnings for this goal type."""
    return await store.get_learnings(goal_type=goal_type, limit=limit)
