"""Task 60 — Amazon seller tool."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings
from models import ToolName
from tools import REGISTRY
from tools.amazon_seller import execute


def test_toolname_amazon_in_enum():
    assert ToolName.AMAZON_SELLER.value == "amazon_seller"


def test_amazon_seller_in_registry():
    assert ToolName.AMAZON_SELLER in REGISTRY


def test_default_marketplace_india():
    assert settings.amazon_marketplace_id == "A21TJRUUN4KGV"


@pytest.mark.asyncio
async def test_get_orders_returns_order_id_field():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "payload": {
            "Orders": [{"AmazonOrderId": "AMZ-123", "OrderStatus": "Pending"}],
        }
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("tools.amazon_seller.httpx.AsyncClient", return_value=mock_client):
        out = await execute(
            "get_orders",
            {"marketplace_id": "A1", "status": "Pending", "days_ago": 7},
        )
    assert isinstance(out, list)
    assert out[0]["order_id"] == "AMZ-123"


@pytest.mark.asyncio
async def test_get_inventory_low_stock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "inventorySummaries": [
            {"sku": "a", "quantity": 3},
            {"sku": "b", "quantity": 50},
        ],
    }
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("tools.amazon_seller.httpx.AsyncClient", return_value=mock_client):
        out = await execute(
            "get_inventory",
            {"marketplace_id": "A1", "low_stock_threshold": 10},
        )
    assert "low_stock_alert" in out
    assert len(out["low_stock_alert"]) >= 1


@pytest.mark.asyncio
async def test_get_sales_report_total_sales():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"total_sales": 1234.5, "units_sold": 10, "by_day": []}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("tools.amazon_seller.httpx.AsyncClient", return_value=mock_client):
        out = await execute(
            "get_sales_report",
            {"start_date": "2026-01-01", "end_date": "2026-01-31", "marketplace_id": "A1"},
        )
    assert out["total_sales"] == 1234.5
