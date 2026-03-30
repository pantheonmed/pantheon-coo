"""Task 68 — HubSpot CRM tool."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings
from models import ToolName
from tools import REGISTRY
from tools import hubspot as hubspot_tool


def test_toolname_hubspot():
    assert ToolName.HUBSPOT.value == "hubspot"
    assert ToolName.HUBSPOT in REGISTRY


@pytest.mark.asyncio
async def test_create_contact_payload(monkeypatch):
    monkeypatch.setattr(settings, "hubspot_api_key", "pat-test-key")
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json = MagicMock(return_value={"id": "99", "properties": {}})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=fake)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("tools.hubspot.httpx.AsyncClient", return_value=mock_cm):
        out = await hubspot_tool.execute(
            "create_contact",
            {"email": "a@b.com", "firstname": "A", "lastname": "B", "company": "Co"},
        )
    assert out["contact_id"] == "99"
    call_kw = mock_client.post.call_args
    assert "crm/v3/objects/contacts" in str(call_kw[0][0])


@pytest.mark.asyncio
async def test_create_deal_requires_dealname_and_amount(monkeypatch):
    monkeypatch.setattr(settings, "hubspot_api_key", "pat-test-key")
    with pytest.raises(ValueError, match="dealname"):
        await hubspot_tool.execute("create_deal", {"amount": 100})
    with pytest.raises(ValueError, match="amount"):
        await hubspot_tool.execute("create_deal", {"dealname": "Big"})


@pytest.mark.asyncio
async def test_get_deals_returns_list(monkeypatch):
    monkeypatch.setattr(settings, "hubspot_api_key", "pat-test-key")
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json = MagicMock(return_value={"results": [{"id": "1"}], "paging": {}})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=fake)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("tools.hubspot.httpx.AsyncClient", return_value=mock_cm):
        out = await hubspot_tool.execute("get_deals", {"limit": 5})
    assert isinstance(out["deals"], list)
    assert out["count"] == 1
