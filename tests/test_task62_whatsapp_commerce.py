"""Task 62 — WhatsApp catalog, orders, commerce tool."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import ToolName
from tools import REGISTRY
from tools import whatsapp_commerce


def test_toolname_whatsapp_commerce():
    assert ToolName.WHATSAPP_COMMERCE.value == "whatsapp_commerce"


def test_whatsapp_commerce_in_registry():
    assert ToolName.WHATSAPP_COMMERCE in REGISTRY


@pytest.mark.asyncio
async def test_send_catalog_payload():
    import whatsapp as wa_mod

    mock_post = AsyncMock(return_value=MagicMock(json=lambda: {}))
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = mock_post

    def fake_cfg():
        m = MagicMock()
        m.whatsapp_access_token = "tok"
        m.whatsapp_phone_number_id = "pid"
        m.whatsapp_catalog_id = "c1"
        return m

    with patch("whatsapp.httpx.AsyncClient", return_value=mock_client):
        with patch("whatsapp._cfg", fake_cfg):
            await wa_mod.send_catalog("+15551234567", "cat99", "Hi")
    body = mock_post.await_args.kwargs["json"]
    assert body.get("type") == "interactive"
    assert body.get("interactive", {}).get("type") == "catalog_message"


@pytest.mark.asyncio
async def test_handle_order_extracts_items():
    import whatsapp as wa

    data = {"product_items": [{"sku": "1"}], "total": 42.0}
    with patch("memory.store.track_event", new_callable=AsyncMock) as tr:
        out = await wa.handle_order(data)
    assert out["items"] == [{"sku": "1"}]
    assert out["total"] == 42.0
    tr.assert_awaited()


@pytest.mark.asyncio
async def test_broadcast_offer_validates_phones():
    with pytest.raises(ValueError, match="Invalid"):
        await whatsapp_commerce.execute(
            "broadcast_offer",
            {"phone_numbers": ["bad"], "offer_text": "x"},
        )


@pytest.mark.asyncio
async def test_order_webhook_triggers_handle_order(client):
    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "pid"},
                            "messages": [
                                {
                                    "from": "15550001111",
                                    "id": "mid",
                                    "timestamp": "1",
                                    "type": "order",
                                    "order": {"product_items": [], "total": 0},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    with patch("security.auth.verify_whatsapp_signature", return_value=True):
        with patch("whatsapp.handle_order", new_callable=AsyncMock) as ho:
            r = client.post("/webhook/whatsapp", json=body)
            assert r.status_code == 200
            assert r.json().get("action") == "order"
            assert ho.await_count >= 1
