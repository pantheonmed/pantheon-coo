"""
agents/reasoning.py
───────────────────
Reasoning Agent — the "thinking" layer of the COO.

Given a raw user goal, this agent:
  1. Understands the true intent (even if the command is vague)
  2. Classifies the task type and complexity
  3. Identifies risks and constraints
  4. Defines measurable success criteria for the Evaluator
  5. Flags ambiguity (if clarification is needed before acting)

This is where the COO "thinks before acting."
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from typing import Any

from pydantic import ValidationError

from agents.base import BaseAgent
from agents.model_router import call_model
from config import settings
from i18n.translations import prompt_respond_in_language_clause
from models import ReasoningInput, ReasoningOutput

logger = logging.getLogger(__name__)

SYSTEM = """
You are the Reasoning Agent of Pantheon COO OS — an autonomous AI Chief Operating Officer.

Your role: deeply understand a goal before any action is taken.

Given a raw goal and context, you must:
1. Rephrase it as a clear, unambiguous, actionable directive
2. Classify the goal type: build | automate | analyze | research | devops | data | communicate
3. Assess complexity: low (1-3 steps) | medium (4-10 steps) | high (10+ steps)
4. Identify risks: what could go wrong? What irreversible actions are involved?
5. State constraints: time, permissions, safety limits
6. Define success criteria: specific, measurable conditions the Evaluator will verify
7. Flag if you need clarification (leave list empty if the goal is clear enough to act)

You have access to context about prior failed attempts and memory snippets from past similar tasks. Use them to reason smarter.

OUTPUT: valid JSON only. Schema:
{
  "understood_goal": "string",
  "goal_type": "build|automate|analyze|research|devops|data|communicate",
  "complexity": "low|medium|high",
  "risks": ["string"],
  "constraints": ["string"],
  "success_criteria": ["measurable condition 1", "..."],
  "clarifications_needed": []
}

If prior attempts failed, analyze why and adjust your reasoning.
Do not include markdown, explanations, or any text outside the JSON.
"""

# Shorter prompts for retries when the first response is not valid JSON.
# Include "Reasoning Agent" so test mocks that route on that phrase still apply.
SIMPLE_SYSTEM = """
You are the Reasoning Agent (compact mode).
You output ONLY valid JSON (no markdown, no prose). Use this exact shape:
{
  "understood_goal": "string",
  "goal_type": "build|automate|analyze|research|devops|data|communicate",
  "complexity": "low|medium|high",
  "risks": [],
  "constraints": [],
  "success_criteria": [],
  "clarifications_needed": []
}
Fill arrays with short strings. If unknown, use sensible defaults and empty arrays where allowed.
""".strip()

MINIMAL_SYSTEM = (
    "You are the Reasoning Agent (minimal JSON). "
    "Output a single JSON object only. Required keys: understood_goal (string), "
    "goal_type (string), complexity (string: low|medium|high), risks (array of strings), "
    "constraints (array), success_criteria (array), clarifications_needed (array). "
    "No markdown fences, no explanation."
)


def _strip_json_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if raw.rstrip().endswith("```"):
            raw = raw[: raw.rfind("```")]
    return raw.strip()


def _fallback_reasoning(inp: ReasoningInput) -> ReasoningOutput:
    g = (inp.raw_goal or "").strip()
    return ReasoningOutput(
        understood_goal=g or "Unspecified goal",
        goal_type="build",
        complexity="medium",
        risks=[
            "Reasoning model output could not be parsed after multiple attempts; "
            "using conservative defaults."
        ],
        constraints=[],
        success_criteria=[
            "Complete the user's stated goal where technically and safely possible."
        ],
        clarifications_needed=[]
        if len(g) > 15
        else ["Please restate your goal more specifically."],
    )


def _parse_reasoning_json(raw: str) -> ReasoningOutput:
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        raise
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return ReasoningOutput(**data)


class ReasoningAgent(BaseAgent[ReasoningInput, ReasoningOutput]):
    name = "reasoning"
    system_prompt = SYSTEM
    max_tokens = 4096

    async def run(self, inp: ReasoningInput) -> ReasoningOutput:
        context_str = ""
        if inp.context:
            context_str = f"\nContext: {inp.context}"
        if inp.memory_snippets:
            context_str += f"\nRelevant past learnings:\n" + "\n".join(
                f"  - {s}" for s in inp.memory_snippets
            )
        if inp.prior_attempts:
            context_str += f"\nPrior failed attempts:\n" + "\n".join(
                f"  - {s}" for s in inp.prior_attempts
            )

        msg = f"Goal: {inp.raw_goal}{context_str}\n\nAnalyze this goal and return the JSON."
        lang = (inp.context or {}).get("language") or settings.default_language
        if lang not in settings.supported_languages:
            lang = settings.default_language
        lang_clause = prompt_respond_in_language_clause(lang)
        full_sys = self.system_prompt + lang_clause

        simple_user = (
            f"Goal: {inp.raw_goal}{context_str}\n\n"
            "Return ONLY the JSON object described in your instructions. No other text."
        )
        minimal_user = (
            f"Goal: {inp.raw_goal}\n\n"
            "Return one JSON object with all required keys. Arrays may be empty except "
            "understood_goal must summarize the goal."
        )

        attempts: list[tuple[str, str, str]] = [
            ("full", full_sys, msg),
            ("simple", SIMPLE_SYSTEM + lang_clause, simple_user),
            ("minimal", MINIMAL_SYSTEM + lang_clause, minimal_user),
        ]

        last_raw = ""
        loop = asyncio.get_event_loop()
        use_fast = getattr(self, "use_fast_model", False)

        for i, (phase, system, user) in enumerate(attempts):
            fn = functools.partial(
                call_model,
                system,
                user,
                use_fast=use_fast,
                max_tokens=self.max_tokens,
            )
            response = await loop.run_in_executor(None, fn)
            self._last_model_used = response.model_used
            self._last_provider = response.provider

            raw = _strip_json_fences(response.text or "")
            last_raw = raw
            logger.debug(
                "[%s] raw model output before parse (attempt %s/%s phase=%s): %s",
                self.name,
                i + 1,
                len(attempts),
                phase,
                raw,
            )
            logger.info(
                "[%s] reasoning parse attempt %s/%s phase=%s raw_len=%s preview=%r",
                self.name,
                i + 1,
                len(attempts),
                phase,
                len(raw),
                raw[:500] + ("..." if len(raw) > 500 else ""),
            )

            try:
                return _parse_reasoning_json(raw)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
                logger.warning(
                    "[%s] JSON parse/validation failed (attempt %s/%s): %s raw_head=%r",
                    self.name,
                    i + 1,
                    len(attempts),
                    e,
                    raw[:800],
                )

        logger.error(
            "[%s] all %s parse attempts failed; returning fallback. last_raw_len=%s head=%r",
            self.name,
            len(attempts),
            len(last_raw),
            last_raw[:1200],
        )
        return _fallback_reasoning(inp)
