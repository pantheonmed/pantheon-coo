"""
agents/tool_builder.py
───────────────────────
Tool Builder Agent — Phase 3. The COO's self-improvement engine.

When the Pattern Detector signals a repeated step sequence, this agent:
  1. Analyzes the pattern and recent task examples
  2. Writes a new Python tool module that encapsulates the sequence
  3. Validates the generated code (syntax check + structure check)
  4. Saves the module to tools/custom/
  5. Registers it live in the dynamic registry
  6. Records it in the DB so future planners can use it

The generated tool follows the exact same interface as built-in tools:
  async def execute(action: str, params: dict) -> Any

This means the Planning Agent can immediately start using the new tool
in future tasks without any code changes.

Why this matters:
  - Repetitive 5-step sequences become 1-step tool calls
  - The COO gets faster and more reliable over time
  - Domain-specific workflows become first-class capabilities
"""
from __future__ import annotations
import ast
import json
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from agents.base import BaseAgent
from config import settings
from pattern_detector import describe_pattern
import memory.store as store
from tools.registry import register_tool

CUSTOM_TOOLS_DIR = Path(__file__).parent.parent / "tools" / "custom"

SYSTEM = """
You are the Tool Builder Agent of Pantheon COO OS.

Your role: write a new Python tool module that encapsulates a repeated sequence of steps.

A tool module must:
1. Be valid Python 3.10+ code
2. Export exactly one function: `async def execute(action: str, params: dict) -> Any`
3. Support at least one action named after the main capability (e.g. "run", "generate", "process")
4. Include clear docstrings
5. Use only stdlib + these available packages: httpx, aiosqlite, pathlib, asyncio, json, subprocess
6. Work within /tmp/pantheon_v2/ as the workspace
7. Handle errors with try/except and return meaningful error dicts
8. Be self-contained (no imports from pantheon_v2 internals)

The tool will be hot-loaded at runtime — it must be safe and runnable immediately.

Output format: JSON with exactly these fields:
{
  "tool_name": "snake_case_name",
  "description": "one sentence describing what this tool does",
  "supported_actions": ["action1", "action2"],
  "code": "full Python source code as a string (use \\n for newlines)"
}

No markdown. No text outside JSON. The code field must be complete, runnable Python.
"""


class ToolBuilderAgent(BaseAgent):
    name = "tool_builder"
    system_prompt = SYSTEM
    max_tokens = 3000

    async def run(
        self,
        pattern_fingerprint: str,
        goal_type: str,
        example_tasks: list[dict],
    ) -> Optional[dict]:
        """
        Build a tool for the given pattern.
        Returns tool metadata dict if successful, None if it failed.
        """
        CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)

        pattern_desc = describe_pattern(pattern_fingerprint)

        # Summarize example tasks that exhibited this pattern
        examples_str = ""
        for i, t in enumerate(example_tasks[:3], 1):
            examples_str += f"\nExample {i}: {t.get('goal','')[:120]}"
            try:
                plan = json.loads(t.get("plan_json", "{}"))
                steps = plan.get("steps", [])[:6]
                for s in steps:
                    examples_str += f"\n  [{s.get('tool')}] {s.get('action')} — {s.get('description','')[:60]}"
            except Exception:
                pass

        msg = f"""Pattern type: {goal_type}
Repeated step sequence: {pattern_desc}
{examples_str}

Build a Python tool module that encapsulates this pattern into reusable actions.
Return the JSON now."""

        from models import MemoryOutput  # reuse simple output model
        # We need a custom output — parse manually
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        for attempt in range(3):
            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": msg}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:raw.rfind("```")]

            try:
                data = json.loads(raw)
                tool_name = data["tool_name"]
                code = data["code"]

                # Validate: must be valid Python
                ast.parse(code)

                # Validate: must have async execute function
                if "async def execute" not in code:
                    raise ValueError("Missing 'async def execute' in generated code")

                # Write to disk
                module_path = CUSTOM_TOOLS_DIR / f"{tool_name}.py"
                module_path.write_text(code, encoding="utf-8")

                # Register live
                register_tool(tool_name, str(module_path))

                # Persist to DB
                tool_id = str(uuid.uuid4())
                await store.save_custom_tool(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    description=data.get("description", ""),
                    module_path=str(module_path),
                    trigger_pattern=pattern_fingerprint,
                    created_from=goal_type,
                )

                print(f"[ToolBuilder] Built and registered: '{tool_name}'")
                return {
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "description": data.get("description", ""),
                    "actions": data.get("supported_actions", []),
                    "module_path": str(module_path),
                }

            except Exception as e:
                if attempt == 2:
                    print(f"[ToolBuilder] Failed after 3 attempts: {e}")
                    return None
                msg += f"\n\nAttempt {attempt+1} failed: {e}. Fix and retry."
                await asyncio.sleep(1)

        return None


# Singleton
_tool_builder = ToolBuilderAgent()


async def maybe_build_tool(
    pattern_fingerprint: str,
    goal_type: str,
) -> Optional[dict]:
    """
    Query recent tasks that match this pattern, then attempt to build a tool.
    Called by the Orchestrator when Pattern Detector signals a repeated pattern.
    """
    # Fetch recent tasks with similar goal_type as examples
    rows = await store.list_tasks(limit=10, status="done")
    matching = [r for r in rows if r.get("goal_type") == goal_type][:3]

    if not matching:
        return None

    return await _tool_builder.run(
        pattern_fingerprint=pattern_fingerprint,
        goal_type=goal_type,
        example_tasks=matching,
    )
