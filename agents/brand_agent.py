"""
agents/brand_agent.py — Personal brand, viral ideas, multi-platform packs.
"""
from __future__ import annotations

import json

from config import settings
from agents.base import BaseAgent
from models import BrandStrategyOutput, ContentPackOutput, ViralIdeasListOutput


class BrandAgent(BaseAgent):
    name = "brand_agent"
    model = settings.claude_model_fast
    max_tokens = 4096
    use_fast_model = True
    system_prompt = """
You are an expert personal branding and social media strategist.
Create actionable, specific strategies — not generic advice.
Always tailor content to Indian market and audience.
Include Hindi/regional language tips where relevant.
"""

    async def create_brand_strategy(
        self,
        name: str,
        profession: str,
        goals: list[str],
        audience: str,
    ) -> dict:
        msg = f"""Build a 90-day personal brand roadmap as JSON:
name: {name}
profession: {profession}
goals: {json.dumps(goals)}
audience: {audience}

Return JSON only:
{{
  "content_pillars": ["..."],
  "posting_schedule": {{"linkedin": "...", "twitter": "..."}},
  "hashtag_strategy": ["..."],
  "ninety_day_plan": ["week1 focus", "week2 focus", ...]
}}
Use key "ninety_day_plan" for the 90-day milestones list (array of strings).
"""
        out = await self._call_claude_async(msg, BrandStrategyOutput)
        return out.model_dump(by_alias=True)

    async def generate_viral_ideas(self, niche: str, count: int = 10) -> list[dict]:
        msg = f"""Niche: {niche}
Generate {count} viral content ideas for Indian LinkedIn/Twitter audience.
Return JSON: {{"ideas": [{{"hook":"...","body_outline":"...","cta":"...","hashtags":["#a"]}}, ...]}}
"""
        out = await self._call_claude_async(msg, ViralIdeasListOutput)
        return [i.model_dump() for i in out.ideas][:count]

    async def create_content_pack(
        self,
        brand_name: str,
        week_number: int,
        topics: list[str],
    ) -> dict:
        msg = f"""Brand: {brand_name}
Week: {week_number}
Topics: {json.dumps(topics)}

Return JSON only:
{{
  "linkedin": ["post1", "post2"],
  "twitter": ["tweet1"],
  "instagram": ["caption1"]
}}
"""
        out = await self._call_claude_async(msg, ContentPackOutput)
        return out.model_dump()
