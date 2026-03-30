"""
agents/suggester.py — suggest next commands after a successful task.
"""
from __future__ import annotations

from config import settings
from models import SuggestionOutput
from agents.base import BaseAgent


class SuggesterAgent(BaseAgent):
    name = "suggester"
    model = settings.claude_model_fast
    max_tokens = 256
    use_fast_model = True
    system_prompt = """
You are a proactive COO assistant.
Given a completed task, suggest 3 logical next commands.
Each under 100 characters. Concrete and actionable.
Return JSON only:
{"suggestions": ["cmd1", "cmd2", "cmd3"]}
"""

    async def run(self, goal: str, summary: str, goal_type: str) -> list[str]:
        msg = f"Completed: {goal}\nResult: {summary}\nType: {goal_type}\nSuggest 3 next steps."
        try:
            out = await self._call_claude_async(msg, SuggestionOutput)
            return list(out.suggestions)[:3]
        except Exception:
            return []
