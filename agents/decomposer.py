"""
agents/decomposer.py
─────────────────────
Phase 5 — Project Decomposer Agent

Given a high-level project goal, this agent breaks it into a set of
independent (or sequentially dependent) sub-tasks that can each be
executed by the standard Reason→Plan→Execute→Evaluate loop.

This is what makes the COO capable of multi-week projects, not just
single-shot commands. A goal like:

  "Build a competitive analysis tool that scrapes 5 competitor websites,
   summarises pricing, generates a comparison report, and emails it weekly"

...gets decomposed into sub-tasks:
  1. Scrape site A
  2. Scrape site B (parallel with 1)
  3. Scrape site C (parallel with 1,2)
  4. Summarise pricing data  [depends on 1,2,3]
  5. Generate comparison report  [depends on 4]
  6. Create weekly schedule for this workflow  [depends on 5]

Each sub-task is an independent NL command the orchestrator can handle.
"""
from __future__ import annotations
import json
from agents.base import BaseAgent
from models import SubTask, ProjectRequest
from pydantic import BaseModel


class DecomposerInput(BaseModel):
    project_name: str
    project_goal: str
    context: dict = {}


class DecomposerOutput(BaseModel):
    summary: str
    sub_tasks: list[SubTask]
    estimated_total_minutes: int = 0
    notes: str = ""


SYSTEM = """
You are the Project Decomposer Agent of Pantheon COO OS.

Your role: break a high-level project goal into an ordered list of executable sub-tasks.

Each sub-task must be:
  1. A self-contained natural language command (like what a user would type)
  2. Specific enough to execute without further clarification
  3. Small enough to complete in a single Reason→Plan→Execute cycle
  4. Assigned a priority (1=low, 2=medium, 3=high)
  5. Given correct depends_on references for tasks that need others to finish first

Guidelines:
  - Independent tasks get empty depends_on (they run in parallel)
  - Max 12 sub-tasks per project — if more needed, group related work
  - Keep each command under 200 characters
  - Order matters: sub_task_id starts at 1

All file/data operations use workspace: /tmp/pantheon_v2/

Output JSON only:
{
  "summary": "one sentence describing what the project will accomplish",
  "estimated_total_minutes": <int>,
  "notes": "any important constraints or warnings",
  "sub_tasks": [
    {
      "sub_task_id": 1,
      "command": "natural language command",
      "depends_on": [],
      "priority": 2,
      "description": "plain English — what this step accomplishes"
    }
  ]
}
"""


class DecomposerAgent(BaseAgent[DecomposerInput, DecomposerOutput]):
    name = "decomposer"
    system_prompt = SYSTEM
    max_tokens = 2048

    async def run(self, inp: DecomposerInput) -> DecomposerOutput:
        msg = (
            f"Project: {inp.project_name}\n"
            f"Goal: {inp.project_goal}\n"
            f"Context: {json.dumps(inp.context) if inp.context else 'none'}\n\n"
            "Break this into sub-tasks and return the JSON."
        )
        return await self._call_claude_async(msg, DecomposerOutput)


# Singleton
_decomposer = DecomposerAgent()


async def decompose(req: ProjectRequest) -> DecomposerOutput:
    return await _decomposer.run(
        DecomposerInput(
            project_name=req.name,
            project_goal=req.goal,
            context=req.context,
        )
    )
