"""Task 35 — finance tool (pure Python)."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import settings
from models import ToolName
from templates import get_template_by_id


@pytest.mark.asyncio
async def test_calculate_gst_18_split(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import finance

    r = await finance.execute(
        "calculate_gst",
        {
            "items": [{"description": "x", "amount": 10000, "gst_rate": 18}],
            "period": "Mar 2026",
        },
    )
    assert r["cgst"] == 900.0
    assert r["sgst"] == 900.0
    assert r["total_tax"] == 1800.0


@pytest.mark.asyncio
async def test_calculate_gst_12_split(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import finance

    r = await finance.execute(
        "calculate_gst",
        {"items": [{"amount": 5000, "gst_rate": 12}], "period": "Q1"},
    )
    assert r["cgst"] == 300.0
    assert r["sgst"] == 300.0


@pytest.mark.asyncio
async def test_generate_invoice_creates_html(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import finance

    r = await finance.execute(
        "generate_invoice",
        {
            "seller_name": "S",
            "seller_gstin": "22AAAAA0000A1Z5",
            "seller_address": "A",
            "buyer_name": "B",
            "buyer_gstin": "33BBBBB0000B1Z5",
            "buyer_address": "Baddr",
            "items": [
                {"description": "Item", "qty": 1, "rate": 100, "gst_rate": 18},
            ],
            "invoice_number": "INV-99",
            "invoice_date": "2026-01-01",
            "due_date": "2026-01-15",
        },
    )
    assert Path(r["file_path"]).exists()
    assert r["total_amount"] > 0


@pytest.mark.asyncio
async def test_generate_pnl_profit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import finance

    r = await finance.execute(
        "generate_pnl",
        {
            "company_name": "Co",
            "period": "Jan",
            "revenue": {"total": 100},
            "expenses": {"cogs": 0, "opex": 60},
        },
    )
    assert r["net_profit"] == 40.0


@pytest.mark.asyncio
async def test_analyze_cashflow_net(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import finance

    r = await finance.execute(
        "analyze_cashflow",
        {
            "income_list": [{"amount": 50000}],
            "expense_list": [{"amount": 30000}],
            "period": "Jan",
        },
    )
    assert r["net_cashflow"] == 20000.0


@pytest.mark.asyncio
async def test_invalid_gst_rate_raises():
    from tools import finance

    with pytest.raises(ValueError, match="Invalid GST"):
        await finance.execute(
            "calculate_gst",
            {"items": [{"amount": 100, "gst_rate": 25}], "period": "x"},
        )


def test_finance_templates():
    for tid in ("gst_report", "invoice_create", "pnl_monthly", "pantheon_med_invoice"):
        assert get_template_by_id(tid)


def test_finance_enum():
    assert ToolName.FINANCE.value == "finance"
