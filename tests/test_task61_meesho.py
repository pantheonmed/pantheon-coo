"""Task 61 — Meesho supplier tool."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import ToolName
from tools import REGISTRY
from tools.meesho import execute


def test_toolname_meesho():
    assert ToolName.MEESHO.value == "meesho"


def test_meesho_in_registry():
    assert ToolName.MEESHO in REGISTRY


@pytest.mark.asyncio
async def test_get_orders_list_format():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"orders": [{"order_id": "M1", "status": "APPROVED"}]}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("tools.meesho.httpx.AsyncClient", return_value=mock_client):
        out = await execute("get_orders", {"status": "APPROVED", "days_ago": 7})
    assert isinstance(out, list)
    assert out[0]["order_id"] == "M1"


@pytest.mark.asyncio
async def test_update_order_status_payload():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("tools.meesho.httpx.AsyncClient", return_value=mock_client):
        out = await execute(
            "update_order_status",
            {"order_id": "O1", "status": "SHIPPED", "tracking_id": "TRK"},
        )
    assert out["payload_sent"]["order_id"] == "O1"
    assert out["payload_sent"]["status"] == "SHIPPED"
    mock_client.post.assert_awaited()
