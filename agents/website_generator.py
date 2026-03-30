"""
agents/website_generator.py — Claude generates full HTML pages (no JSON wrapper).
"""
from __future__ import annotations

import asyncio

from config import settings
from agents.base import BaseAgent
from agents.model_router import call_model


class WebsiteGeneratorAgent(BaseAgent):
    name = "website_generator"
    model = settings.claude_model_fast
    max_tokens = 4096
    use_fast_model = True
    system_prompt = """
Generate complete, beautiful, mobile-responsive HTML pages.
Rules:
- Pure HTML/CSS/JS (no external frameworks/CDNs)
- Mobile responsive with @media queries in <style>
- All CSS in <style> tag, all JS in <script> tag at bottom
- Professional design
- Proper meta tags for SEO in <head>
- Fast loading, no heavy assets
Return ONLY the complete HTML document. Nothing else — no markdown fences.
"""

    async def generate_html(self, instruction: str) -> str:
        def _sync() -> str:
            r = call_model(
                self.system_prompt,
                instruction,
                use_fast=True,
                max_tokens=self.max_tokens,
            )
            raw = (r.text or "").strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:])
                if raw.rstrip().endswith("```"):
                    raw = raw[: raw.rfind("```")].rstrip()
            return raw.strip()

        return await asyncio.to_thread(_sync)
