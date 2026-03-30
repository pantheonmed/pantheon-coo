"""
agents/base.py
──────────────
Base class for all Pantheon COO agents.

Every agent:
  - Has a name and a system prompt (its "personality")
  - Calls Claude with typed input → typed output
  - Parses JSON output and retries if malformed
  - Logs to the memory store

Subclass this and implement `system_prompt` + `run()`.
"""
from __future__ import annotations
import json
import asyncio
from typing import TypeVar, Generic, Type
from pydantic import BaseModel
from config import settings

TInput  = TypeVar("TInput",  bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class BaseAgent(Generic[TInput, TOutput]):
    name: str = "agent"
    system_prompt: str = ""
    model: str = settings.claude_model
    max_tokens: int = 2048
    max_parse_retries: int = 2
    use_fast_model: bool = False
    _last_model_used: str = ""
    _last_provider: str = ""

    async def run(self, input_data: TInput) -> TOutput:
        raise NotImplementedError

    # ─────────────────────────────────────────────────────────────────
    # Core Claude call — handles JSON parsing + retry on bad output
    # ─────────────────────────────────────────────────────────────────

    def _call_claude(
        self,
        user_message: str,
        output_model: Type[TOutput],
        *,
        temperature: float | None = None,
        system_prompt_override: str | None = None,
    ) -> TOutput:
        """
        Model call (Claude primary, OpenAI fallback) returning a parsed Pydantic model.
        Retries up to max_parse_retries if output is not valid JSON.
        Phase 4: Uses ModelRouter for automatic provider fallback.
        """
        from agents.model_router import call_model
        use_fast = getattr(self, "use_fast_model", False)
        sys_prompt = (
            system_prompt_override
            if system_prompt_override is not None
            else self.system_prompt
        )

        current_user = user_message
        last_err = None

        for attempt in range(self.max_parse_retries + 1):
            response = call_model(
                sys_prompt,
                current_user,
                use_fast=use_fast,
                max_tokens=self.max_tokens,
            )
            raw = response.text.strip()

            # Track which model served this agent
            self._last_model_used = response.model_used
            self._last_provider = response.provider

            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[: raw.rfind("```")]

            try:
                data = json.loads(raw)
                return output_model(**data)
            except (json.JSONDecodeError, Exception) as e:
                last_err = e
                if attempt < self.max_parse_retries:
                    current_user = (
                        f"{current_user}\n\n---\nPrevious response was not valid JSON. "
                        f"Error: {e}. Return ONLY the corrected JSON object, nothing else."
                    )

        raise ValueError(
            f"[{self.name}] Failed to parse model output after "
            f"{self.max_parse_retries + 1} attempts. Last error: {last_err}"
        )

    async def _call_claude_async(
        self,
        user_message: str,
        output_model: Type[TOutput],
        *,
        system_prompt_override: str | None = None,
    ) -> TOutput:
        """Async wrapper — runs the sync call in a thread pool."""
        import functools

        loop = asyncio.get_event_loop()
        fn = functools.partial(
            self._call_claude,
            user_message,
            output_model,
            system_prompt_override=system_prompt_override,
        )
        return await loop.run_in_executor(None, fn)
