"""
agents/call_agent.py — Business phone call script generation (voice AI helper).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent


class CallScriptInput(BaseModel):
    """Unused placeholder for BaseAgent type params (scripts built via generate_call_script)."""

    pass


class CallScriptOutput(BaseModel):
    script: str = Field(..., description="Natural spoken script for the call")


class CallAgent(BaseAgent[CallScriptInput, CallScriptOutput]):
    name = "call_agent"
    system_prompt = """
You are a professional business phone call agent.
You speak clearly and professionally.
You handle: quotation requests, follow-ups,
appointment scheduling, customer queries.
Always introduce yourself as COO assistant.
Keep responses concise for phone conversation.
End call politely when task is done.
Return ONLY valid JSON: {"script": "..."} with the full spoken script as one string.
""".strip()
    use_fast_model = True

    async def generate_call_script(
        self,
        purpose: str,
        recipient_name: str,
        key_points: list[str],
    ) -> str:
        pts = "\n".join(f"- {p}" for p in (key_points or []))
        user = (
            f"Purpose: {purpose}\n"
            f"Recipient name: {recipient_name}\n"
            f"Key points to cover:\n{pts}\n\n"
            f"Write the phone script as natural dialogue (COO assistant speaking)."
        )
        out = await self._call_claude_async(user, CallScriptOutput)
        return (out.script or "").strip()
