"""
agents/confidence.py
─────────────────────
Phase 4 — Confidence Scoring

Every major agent output is scored for confidence before the system acts on it.
Low-confidence outputs trigger additional verification or a re-run.

Confidence levels:
  HIGH   (>= 0.85) — proceed normally
  MEDIUM (0.65–0.85) — proceed with extra logging, flag for review
  LOW    (< 0.65) — trigger re-reasoning or ask for clarification

The scorer is lightweight (uses fast model) and runs synchronously
between agent calls in the orchestrator.

What it evaluates:
  - Reasoning: Is the goal interpretation coherent and complete?
  - Planning:  Are the steps specific, ordered, and achievable?
  - Execution: Did steps produce outputs that match expectations?
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Literal

from agents.model_router import call_model
from config import settings

ConfidenceLevel = Literal["high", "medium", "low"]

CONFIDENCE_SYSTEM = """
You are a confidence evaluator for an AI execution system.

Given an agent's output, score your confidence that it is correct and complete.

Return JSON only:
{
  "score": 0.0-1.0,
  "level": "high|medium|low",
  "reasoning": "one sentence explaining the score",
  "flags": ["specific concern if any"]
}

Scoring guide:
  0.9+ = output is clear, specific, complete, and unambiguous
  0.7-0.9 = mostly good but has minor gaps or assumptions
  0.5-0.7 = significant uncertainty, vague steps, or risky assumptions
  < 0.5 = output is unclear, contradictory, or likely wrong
"""


@dataclass
class ConfidenceResult:
    score: float
    level: ConfidenceLevel
    reasoning: str
    flags: list[str]


def _level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.85:
        return "high"
    elif score >= 0.65:
        return "medium"
    return "low"


def score_reasoning(goal: str, reasoning_output: dict) -> ConfidenceResult:
    """Score a ReasoningOutput for clarity and completeness."""
    user = f"""Goal: {goal}

Reasoning output:
{json.dumps(reasoning_output, indent=2)[:1200]}

Is this reasoning clear, complete, and well-grounded? Score it."""
    return _score(user)


def score_plan(goal: str, plan_output: dict) -> ConfidenceResult:
    """Score a PlanningOutput for executability."""
    user = f"""Goal: {goal}

Execution plan:
{json.dumps(plan_output, indent=2)[:1500]}

Are these steps specific, correctly ordered, and achievable with the available tools?
Flag any steps that are vague, missing parameters, or likely to fail."""
    return _score(user)


def _score(user_message: str) -> ConfidenceResult:
    try:
        response = call_model(
            CONFIDENCE_SYSTEM,
            user_message,
            use_fast=True,    # always use fast model for confidence scoring
            max_tokens=256,
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:raw.rfind("```")]

        data = json.loads(raw)
        score = float(data.get("score", 0.75))
        return ConfidenceResult(
            score=score,
            level=_level_from_score(score),
            reasoning=data.get("reasoning", ""),
            flags=data.get("flags", []),
        )
    except Exception as e:
        # If scorer itself fails, return medium confidence so we don't block execution
        return ConfidenceResult(
            score=0.70,
            level="medium",
            reasoning=f"Confidence scorer error: {e}",
            flags=["scorer_unavailable"],
        )
