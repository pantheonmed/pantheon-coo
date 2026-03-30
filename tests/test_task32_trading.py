"""Task 32 — market_data tool, sandbox, trading analyst, templates."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.trading_analyst import TradingAnalystAgent
from models import ExecutionStep, ToolName, TradingAnalysisOutput
from security.sandbox import SecurityError, validate_step
from templates import TEMPLATES, get_template_by_id


@pytest.mark.asyncio
async def test_get_quote_returns_price_shape(monkeypatch):
    fake = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 100.5,
                        "previousClose": 99.0,
                        "regularMarketVolume": 12345,
                    }
                }
            ]
        }
    }

    async def fake_get(url, params=None):
        return fake

    with patch("tools.market_data._get_json", new_callable=AsyncMock, side_effect=fake_get):
        from tools import market_data

        out = await market_data.execute(
            "get_quote", {"symbol": "RELIANCE.NS"}
        )
    assert out["price"] == 100.5
    assert out["volume"] == 12345
    assert "change_pct" in out


def test_invalid_symbol_blocked_by_sandbox():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.MARKET_DATA,
        action="get_quote",
        params={"symbol": "rm -rf"},
    )
    with pytest.raises(SecurityError):
        validate_step(step)


@pytest.mark.asyncio
async def test_trading_analyst_output_has_disclaimer():
    agent = TradingAnalystAgent()
    data = await agent.analyze("RELIANCE.NS", {"price": 2500})
    assert "disclaimer" in data
    assert "educational" in data["disclaimer"].lower() or "SEBI" in data["disclaimer"]


def test_toolname_market_data_enum():
    assert ToolName.MARKET_DATA.value == "market_data"


def test_market_data_in_registry():
    from tools import REGISTRY

    assert ToolName.MARKET_DATA in REGISTRY


def test_trading_templates_exist():
    for tid in ("stock_analysis", "portfolio_report", "market_screener"):
        t = get_template_by_id(tid)
        assert t is not None
        assert "command" in t


def test_trading_analysis_output_model():
    m = TradingAnalysisOutput(
        symbol="X",
        trend="neutral",
        summary="a. b.",
        key_levels={"support": 1.0, "resistance": 2.0},
        risk_factors=["r"],
        disclaimer="Not advice.",
    )
    assert m.trend == "neutral"
