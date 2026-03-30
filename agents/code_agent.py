"""
agents/code_agent.py — Code generation / review helper (Python-focused).
"""
from __future__ import annotations

from config import settings
from agents.base import BaseAgent


class CodeAgent(BaseAgent):
    name = "code_agent"
    model = settings.claude_model_fast
    max_tokens = 4096
    use_fast_model = True
    system_prompt = """
You are an expert Python developer.
Generate clean, production-ready code.
Always include:
- Type hints
- Docstrings
- Error handling
- No hardcoded secrets
Return only the code, no explanation.
"""
