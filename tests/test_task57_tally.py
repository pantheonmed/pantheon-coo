"""Task 57 — Tally tool integration."""
from unittest.mock import AsyncMock, patch

import pytest

from models import ToolName
from tools import tally


def test_toolname_tally_in_enum():
    assert ToolName.TALLY.value == "tally"


@pytest.mark.asyncio
async def test_get_ledgers_returns_list_format():
    xml = "<RESPONSE><NAME>Ledger A</NAME><NAME>Ledger B</NAME></RESPONSE>"
    with patch("tools.tally._post_tally", new_callable=AsyncMock, return_value=xml):
        out = await tally.execute("get_ledgers", {})
    assert "ledgers" in out
    assert isinstance(out["ledgers"], list)


@pytest.mark.asyncio
async def test_create_voucher_balanced_dr_cr():
    with patch("tools.tally._post_tally", new_callable=AsyncMock, return_value="<R><VOUCHERNUMBER>1</VOUCHERNUMBER></R>"):
        out = await tally.execute(
            "create_voucher",
            {
                "voucher_type": "Payment",
                "date": "2026-03-01",
                "narration": "test",
                "ledger_entries": [
                    {"ledger": "A", "amount": 100, "dr_cr": "Dr"},
                    {"ledger": "B", "amount": 100, "dr_cr": "Cr"},
                ],
            },
        )
    assert out.get("success") is True


@pytest.mark.asyncio
async def test_create_voucher_unbalanced_raises():
    with pytest.raises(ValueError, match="balance"):
        await tally.execute(
            "create_voucher",
            {
                "voucher_type": "Payment",
                "date": "2026-03-01",
                "narration": "x",
                "ledger_entries": [
                    {"ledger": "A", "amount": 100, "dr_cr": "Dr"},
                    {"ledger": "B", "amount": 50, "dr_cr": "Cr"},
                ],
            },
        )


@pytest.mark.asyncio
async def test_sync_invoices_counts(tmp_path):
    inv = tmp_path / "i1.json"
    inv.write_text('{"amount": 10, "date": "2026-01-01", "customer_ledger": "C"}')
    with patch("tools.tally._post_tally", new_callable=AsyncMock, return_value="<OK/>"):
        out = await tally.execute("sync_invoices", {"invoices_path": str(tmp_path)})
    assert out["synced"] == 1
    assert out["failed"] == 0
