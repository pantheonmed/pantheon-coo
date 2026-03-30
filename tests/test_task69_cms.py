"""Task 69 — WordPress + Shopify tools."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings
from models import ToolName
from tools import REGISTRY
from tools import shopify as shopify_tool
from tools import wordpress as wordpress_tool


def test_toolnames():
    assert ToolName.WORDPRESS.value == "wordpress"
    assert ToolName.SHOPIFY.value == "shopify"
    assert ToolName.WORDPRESS in REGISTRY
    assert ToolName.SHOPIFY in REGISTRY


@pytest.mark.asyncio
async def test_wordpress_create_post_returns_id(monkeypatch):
    monkeypatch.setattr(settings, "wordpress_site_url", "https://example.com")
    monkeypatch.setattr(settings, "wordpress_username", "u")
    monkeypatch.setattr(settings, "wordpress_app_password", "p")
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json = MagicMock(return_value={"id": 42, "link": "https://example.com/?p=42"})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=fake)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("tools.wordpress.httpx.AsyncClient", return_value=mock_cm):
        out = await wordpress_tool.execute(
            "create_post",
            {"title": "T", "content": "C", "status": "draft"},
        )
    assert out["post_id"] == 42
    assert "url" in out


@pytest.mark.asyncio
async def test_shopify_get_orders_list(monkeypatch):
    monkeypatch.setattr(settings, "shopify_store_domain", "test-shop.myshopify.com")
    monkeypatch.setattr(settings, "shopify_access_token", "tok")
    fake = MagicMock()
    fake.raise_for_status = MagicMock()
    fake.json = MagicMock(return_value={"orders": [{"id": 1}, {"id": 2}]})
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=fake)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    with patch("tools.shopify.httpx.AsyncClient", return_value=mock_cm):
        out = await shopify_tool.execute("get_orders", {"status": "open", "limit": 10})
    assert isinstance(out["orders"], list)
    assert out["count"] == 2
