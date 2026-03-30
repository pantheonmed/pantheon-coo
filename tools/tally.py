"""
tools/tally.py — Tally Prime HTTP/XML bridge (REST-style POST body).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from config import settings


def _base_url() -> str:
    return f"http://{settings.tally_host}:{settings.tally_port}"


def _envelope(body_inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<ENVELOPE>"
        "<HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>"
        "<TYPE>DATA</TYPE><ID>COO</ID></HEADER>"
        f"<BODY>{body_inner}</BODY>"
        "</ENVELOPE>"
    )


async def _post_tally(body_inner: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(_base_url(), content=_envelope(body_inner))
        r.raise_for_status()
        return r.text


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()
    if a == "get_ledgers":
        xml = "<DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES></DESC>"
        text = await _post_tally(xml)
        names = re.findall(r"<NAME[^>]*>([^<]+)</NAME>", text, re.I)
        return {"ledgers": [n.strip() for n in names if n.strip()]}

    if a == "get_balance":
        ledger = (params.get("ledger_name") or "").strip()
        fd = (params.get("from_date") or "").strip()
        td = (params.get("to_date") or "").strip()
        xml = (
            f"<DESC><STATICVARIABLES>"
            f"<SVFROMDATE>{fd}</SVFROMDATE><SVTODATE>{td}</SVTODATE>"
            f"<LEDGERNAME>{ledger}</LEDGERNAME>"
            f"</STATICVARIABLES></DESC>"
        )
        text = await _post_tally(xml)
        return {
            "ledger_name": ledger,
            "from_date": fd,
            "to_date": td,
            "opening": 0.0,
            "closing": 0.0,
            "debit_total": 0.0,
            "credit_total": 0.0,
            "raw_excerpt": text[:500],
        }

    if a == "create_voucher":
        vtype = (params.get("voucher_type") or "Sales").strip()
        date = (params.get("date") or "").strip()
        narration = (params.get("narration") or "").strip()
        entries = params.get("ledger_entries") or []
        dr = 0.0
        cr = 0.0
        lines = []
        for e in entries:
            amt = float(e.get("amount") or 0)
            side = (e.get("dr_cr") or "Dr").strip()
            ledger = (e.get("ledger") or "").strip()
            lines.append(f"<LINE><LEDGER>{ledger}</LEDGER><AMOUNT>{amt}</AMOUNT><SIDE>{side}</SIDE></LINE>")
            if side.lower().startswith("d"):
                dr += amt
            else:
                cr += amt
        if abs(dr - cr) > 0.01:
            raise ValueError("Dr/Cr entries must balance (sum Dr == sum Cr)")
        inner = (
            f"<VOUCHER><TYPE>{vtype}</TYPE><DATE>{date}</DATE>"
            f"<NARRATION>{narration}</NARRATION>{''.join(lines)}</VOUCHER>"
        )
        text = await _post_tally(inner)
        num = re.search(r"<VOUCHERNUMBER[^>]*>([^<]+)</VOUCHERNUMBER>", text, re.I)
        return {
            "voucher_number": (num.group(1).strip() if num else "0"),
            "success": True,
            "response_excerpt": text[:300],
        }

    if a == "get_trial_balance":
        fd = (params.get("from_date") or "").strip()
        td = (params.get("to_date") or "").strip()
        xml = (
            f"<DESC><STATICVARIABLES>"
            f"<SVFROMDATE>{fd}</SVFROMDATE><SVTODATE>{td}</SVTODATE>"
            f"</STATICVARIABLES></DESC>"
        )
        text = await _post_tally(xml)
        return {"from_date": fd, "to_date": td, "trial_balance_text": text[:4000]}

    if a == "sync_invoices":
        inv_path = Path((params.get("invoices_path") or "").strip() or "/tmp/pantheon_v2/invoices")
        synced = 0
        failed = 0
        errors: list[str] = []
        if not inv_path.is_dir():
            return {"synced": 0, "failed": 0, "errors": [f"not a directory: {inv_path}"]}
        for p in sorted(inv_path.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                amt = float(data.get("amount") or 0)
                customer = (data.get("customer_ledger") or "Sales").strip()
                inner = (
                    "<VOUCHER><TYPE>Sales</TYPE>"
                    f"<DATE>{data.get('date', '')}</DATE>"
                    f"<NARRATION>Invoice {p.name}</NARRATION>"
                    f"<LINE><LEDGER>{customer}</LEDGER><AMOUNT>{amt}</AMOUNT><SIDE>Dr</SIDE></LINE>"
                    f"<LINE><LEDGER>Sales</LEDGER><AMOUNT>{amt}</AMOUNT><SIDE>Cr</SIDE></LINE>"
                    "</VOUCHER>"
                )
                await _post_tally(inner)
                synced += 1
            except Exception as e:
                failed += 1
                errors.append(f"{p.name}: {e}")
        return {"synced": synced, "failed": failed, "errors": errors}

    raise ValueError(f"Unknown tally action: {action}")
