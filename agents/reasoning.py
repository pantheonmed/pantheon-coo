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
from agents.base import BaseAgent
from config import settings
from i18n.translations import prompt_respond_in_language_clause
from models import ReasoningInput, ReasoningOutput


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


class ReasoningAgent(BaseAgent[ReasoningInput, ReasoningOutput]):
    name = "reasoning"
    system_prompt = SYSTEM
    max_tokens = 1024

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
        sys = self.system_prompt + prompt_respond_in_language_clause(lang)
        return await self._call_claude_async(
            msg, ReasoningOutput, system_prompt_override=sys
        )
