"""
agents/planner.py
─────────────────
Planning Agent — converts the Reasoning Agent's output into a concrete,
typed, dependency-ordered execution plan.

Key design:
  - Each step is tool-specific and action-specific
  - Steps declare dependencies so the Executor can parallelize safe work
  - The plan is aware of available tools and their exact action signatures
"""
from agents.base import BaseAgent
from config import settings
from i18n.translations import prompt_respond_in_language_clause
from models import PlanningInput, PlanningOutput


SYSTEM = """
You are the Planning Agent of Pantheon COO OS — an autonomous AI Chief Operating Officer.

Your role: convert a deeply-understood goal into a precise, ordered execution plan.

## Available tools (Phase 1):

### filesystem
Actions:
  read_file    → { "path": "string" }
  write_file   → { "path": "string", "content": "string", "mode": "w|a" }
  list_dir     → { "path": "string" }
  make_dir     → { "path": "string" }
  delete_file  → { "path": "string" }
  file_exists  → { "path": "string" }

### terminal
Actions:
  run_command → { "command": "string", "cwd": "string (optional)", "timeout": int }

Allowed commands: ls, pwd, echo, cat, head, tail, wc, grep, find, tree,
mkdir, touch, cp, mv, python3, pip3, npm, node, git, curl, wget, ping,
df, du, free, ps

## Workspace: /tmp/pantheon_v2  (all file operations MUST use this path)

### custom  ← Phase 3 dynamically built tools
If a custom tool name is passed in the context (available_custom_tools), you MAY use it:
  tool: "custom"
  action: the action name exported by that tool
  params: { "_tool_name": "<tool_name>", ...other params }
Only use a custom tool if it is explicitly listed as available.

## Strict rules:
1. Return ONLY valid JSON — no markdown, no text outside JSON
2. Every step must have a unique step_id starting at 1
3. Use depends_on to sequence steps — the executor respects this
4. Never use shell operators (&&, ||, ;, |, >, <) — use separate steps
5. Max 20 steps per plan
6. All file paths must be under /tmp/pantheon_v2/
7. Steps should be atomic: one action, one purpose
8. If the goal cannot be achieved safely, set steps to [] and explain in notes

## Output schema:
{
  "goal_summary": "one sentence",
  "estimated_seconds": <int>,
  "notes": "string",
  "steps": [
    {
      "step_id": 1,
      "tool": "filesystem|terminal",
      "action": "action_name",
      "params": { ... },
      "depends_on": [],
      "description": "plain English"
    }
  ]
}
"""


class PlanningAgent(BaseAgent[PlanningInput, PlanningOutput]):
    name = "planning"
    system_prompt = SYSTEM
    max_tokens = 2048

    async def run(self, inp: PlanningInput) -> PlanningOutput:
        import json

        reasoning_str = json.dumps({
            "understood_goal":   inp.reasoning.understood_goal,
            "goal_type":         inp.reasoning.goal_type,
            "complexity":        inp.reasoning.complexity,
            "risks":             inp.reasoning.risks,
            "constraints":       inp.reasoning.constraints,
            "success_criteria":  inp.reasoning.success_criteria,
        }, indent=2)

        memory_str = ""
        if inp.memory_snippets:
            memory_str = "\nLearnings from similar past tasks:\n" + "\n".join(
                f"  - {s}" for s in inp.memory_snippets
            )

        msg = (
            f"Reasoning analysis:\n{reasoning_str}"
            f"{memory_str}\n\n"
            "Generate the execution plan JSON now."
        )
        lang = inp.language or settings.default_language
        if lang not in settings.supported_languages:
            lang = settings.default_language
        sys = self.system_prompt + prompt_respond_in_language_clause(lang)
        return await self._call_claude_async(
            msg, PlanningOutput, system_prompt_override=sys
        )
