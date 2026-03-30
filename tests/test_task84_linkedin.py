"""Task 84 — LinkedIn tool + templates + rate guard."""
from __future__ import annotations

import pytest

from models import ToolName
from templates import TEMPLATES
from tools import linkedin


@pytest.mark.asyncio
async def test_search_people_list_format():
    out = await linkedin.execute(
        "search_people", {"keywords": "founder", "location": "India", "limit": 5}
    )
    assert "profiles" in out
    assert isinstance(out["profiles"], list)


@pytest.mark.asyncio
async def test_linkedin_rate_limit_after_50(monkeypatch):
    linkedin.reset_linkedin_daily_for_tests()
    for _ in range(50):
        await linkedin._bump_action_count()
    with pytest.raises(ValueError, match="rate limit|LinkedIn"):
        await linkedin.assert_linkedin_rate_allow()


def test_toolname_linkedin_enum():
    assert ToolName.LINKEDIN.value == "linkedin"


def test_linkedin_templates_exist():
    ids = {t["id"] for t in TEMPLATES}
    assert "linkedin_outreach" in ids
    assert "linkedin_post_creator" in ids
    assert "nishant_linkedin" in ids
