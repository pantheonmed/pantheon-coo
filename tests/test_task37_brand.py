"""Task 37 — brand_agent + /brand/* + templates."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.brand_agent import BrandAgent
from templates import TEMPLATES, get_template_by_id


@pytest.mark.asyncio
async def test_brand_strategy_dict_keys():
    ag = BrandAgent()
    d = await ag.create_brand_strategy("N", "Dev", ["grow"], "founders")
    assert "content_pillars" in d
    assert "posting_schedule" in d


@pytest.mark.asyncio
async def test_viral_ideas_list_len():
    ag = BrandAgent()
    ideas = await ag.generate_viral_ideas("SaaS", 10)
    assert isinstance(ideas, list)
    assert len(ideas) == 10


def test_post_brand_strategy_200(client: TestClient):
    r = client.post(
        "/brand/strategy",
        json={
            "name": "Test User",
            "profession": "Engineer",
            "goals": ["visibility"],
            "audience": "B2B",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "content_pillars" in body


def test_post_brand_viral_list(client: TestClient):
    r = client.post(
        "/brand/viral-ideas",
        json={"niche": "fintech", "count": 10},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) == 10


def test_brand_agent_system_prompt_indian_market():
    assert "Indian market" in BrandAgent.system_prompt


def test_three_brand_templates():
    for tid in ("personal_brand_audit", "viral_post_generator", "nishant_brand"):
        assert get_template_by_id(tid)
