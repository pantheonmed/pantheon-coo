"""Task 49 — Zoho CRM tool."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ToolName
from tools import REGISTRY
from tools import zoho_crm as zoho_mod


@pytest.mark.asyncio
async def test_create_lead_payload(monkeypatch):
    monkeypatch.setattr(settings, "zoho_access_token", "tok")
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(
                return_value={"data": [{"details": {"id": "L1"}}]},
            )
            return resp

    with patch("tools.zoho_crm.httpx.AsyncClient", return_value=FakeClient()):
        await zoho_mod.execute(
            "create_lead",
            {
                "first_name": "A",
                "last_name": "B",
                "email": "a@b.com",
                "phone": "+911",
                "company": "Co",
            },
        )
    assert "zohoapis.in" in captured["url"]
    assert captured["json"]["data"][0]["Email"] == "a@b.com"


@pytest.mark.asyncio
async def test_search_leads_list(monkeypatch):
    monkeypatch.setattr(settings, "zoho_access_token", "tok")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, params=None, headers=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"data": [{"Company": "X"}]})
            return resp

    with patch("tools.zoho_crm.httpx.AsyncClient", return_value=FakeClient()):
        rows = await zoho_mod.execute("search_leads", {"query": "acme", "limit": 5})
    assert isinstance(rows, list)
    assert rows[0]["Company"] == "X"


@pytest.mark.asyncio
async def test_create_deal_requires_amount_and_stage():
    with pytest.raises(ValueError, match="amount"):
        await zoho_mod.execute(
            "create_deal",
            {"deal_name": "D", "account_name": "A", "stage": "Open", "close_date": "2026-12-31"},
        )


def test_toolname_zoho_enum():
    assert ToolName.ZOHO_CRM.value == "zoho_crm"


def test_zoho_in_registry():
    assert ToolName.ZOHO_CRM in REGISTRY
