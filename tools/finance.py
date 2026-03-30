"""
tools/finance.py — GST, invoices, P&L, cashflow, expense categories (pure Python).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config import settings

_GST_RATES = frozenset({0, 5, 12, 18, 28})


def _ws_root() -> Path:
    return Path(settings.workspace_dir).resolve()


def _validate_gst_rate(rate: Any) -> float:
    r = int(rate) if isinstance(rate, (int, float)) and float(rate).is_integer() else int(float(rate))
    if r not in _GST_RATES:
        raise ValueError(f"Invalid GST rate {r}%; allowed: {sorted(_GST_RATES)}")
    return float(r)


def _calculate_gst(p: dict[str, Any]) -> dict[str, Any]:
    items = p.get("items") or []
    cgst = sgst = igst = 0.0
    taxable = 0.0
    for it in items:
        amt = float(it.get("amount", 0))
        rate = _validate_gst_rate(it.get("gst_rate", 0))
        taxable += amt
        tax = amt * rate / 100.0
        cgst += tax / 2.0
        sgst += tax / 2.0
    total_tax = cgst + sgst + igst
    net = taxable + total_tax
    return {
        "cgst": round(cgst, 2),
        "sgst": round(sgst, 2),
        "igst": round(igst, 2),
        "total_tax": round(total_tax, 2),
        "net_payable": round(net, 2),
        "taxable_value": round(taxable, 2),
        "period": str(p.get("period") or ""),
    }


def _generate_invoice(p: dict[str, Any]) -> dict[str, Any]:
    inv_dir = _ws_root() / "invoices"
    inv_dir.mkdir(parents=True, exist_ok=True)
    num = str(p.get("invoice_number") or "INV1")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", num)[:60]
    path = inv_dir / f"invoice_{safe}.html"
    items = p.get("items") or []
    rows = ""
    subtotal = 0.0
    tax_total = 0.0
    for it in items:
        desc = str(it.get("description", ""))
        qty = float(it.get("qty", 1))
        rate = float(it.get("rate", 0))
        gst_r = _validate_gst_rate(it.get("gst_rate", 18))
        line = qty * rate
        tax = line * gst_r / 100.0
        subtotal += line
        tax_total += tax
        rows += f"<tr><td>{desc}</td><td>{qty}</td><td>{rate}</td><td>{gst_r}%</td><td>{line+tax:.2f}</td></tr>"
    grand = subtotal + tax_total
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Invoice {num}</title></head>
<body><h1>Tax Invoice</h1>
<p><b>Seller:</b> {p.get("seller_name","")} — GSTIN {p.get("seller_gstin","")}<br>{p.get("seller_address","")}</p>
<p><b>Buyer:</b> {p.get("buyer_name","")} — GSTIN {p.get("buyer_gstin","")}<br>{p.get("buyer_address","")}</p>
<p>Invoice #{num} Date {p.get("invoice_date","")} Due {p.get("due_date","")}</p>
<table border="1"><tr><th>Item</th><th>Qty</th><th>Rate</th><th>GST%</th><th>Total</th></tr>{rows}</table>
<p>Subtotal: {subtotal:.2f} Tax: {tax_total:.2f} <b>Grand: {grand:.2f}</b></p></body></html>"""
    path.write_text(html, encoding="utf-8")
    return {
        "file_path": str(path),
        "total_amount": round(grand, 2),
        "tax_amount": round(tax_total, 2),
    }


def _generate_pnl(p: dict[str, Any]) -> dict[str, Any]:
    rev = p.get("revenue") or {}
    exp = p.get("expenses") or {}
    if isinstance(rev, dict):
        revenue = float(rev.get("total", 0) or 0)
    else:
        revenue = float(rev or 0)
    if isinstance(exp, dict):
        cogs = float(exp.get("cogs", 0) or 0)
        opex = float(exp.get("opex", exp.get("total", 0)) or 0)
    else:
        cogs = 0.0
        opex = float(exp or 0)
    gross = revenue - cogs
    net = revenue - cogs - opex
    ebitda = gross - opex * 0.9
    margin = (net / revenue * 100.0) if revenue else 0.0
    report = _ws_root() / "finance"
    report.mkdir(parents=True, exist_ok=True)
    fn = re.sub(r"[^a-z0-9_]+", "_", str(p.get("period", "pnl")).lower())[:40]
    path = report / f"pnl_{fn}.md"
    md = f"# P&L {p.get('company_name','')}\nPeriod: {p.get('period','')}\n\nRevenue: {revenue}\nCOGS: {cogs}\nOpex: {opex}\nGross: {gross}\nNet: {net}\nEBITDA est: {ebitda}\nMargin %: {margin:.2f}\n"
    path.write_text(md, encoding="utf-8")
    return {
        "gross_profit": round(gross, 2),
        "net_profit": round(net, 2),
        "ebitda": round(ebitda, 2),
        "margin_pct": round(margin, 2),
        "report_path": str(path),
    }


def _analyze_cashflow(p: dict[str, Any]) -> dict[str, Any]:
    inc = p.get("income_list") or []
    exp = p.get("expense_list") or []
    tin = sum(float(x.get("amount", 0)) for x in inc if isinstance(x, dict))
    tex = sum(float(x.get("amount", 0)) for x in exp if isinstance(x, dict))
    net = tin - tex
    burn = tex / max(len(exp), 1) if exp else 0.0
    runway = (net / burn) if burn > 0 and net > 0 else None
    return {
        "net_cashflow": round(net, 2),
        "burn_rate": round(burn, 2),
        "runway_months": round(runway, 2) if runway is not None else None,
        "period": str(p.get("period") or ""),
    }


def _categorize_expenses(p: dict[str, Any]) -> dict[str, Any]:
    txs = p.get("transactions") or []
    cats: dict[str, list[dict[str, Any]]] = {
        "travel": [],
        "software": [],
        "meals": [],
        "other": [],
    }
    for t in txs:
        if not isinstance(t, dict):
            continue
        desc = (t.get("description") or "").lower()
        amt = float(t.get("amount", 0))
        entry = {"date": t.get("date"), "description": t.get("description"), "amount": amt}
        if any(w in desc for w in ("uber", "flight", "hotel", "taxi")):
            cats["travel"].append(entry)
        elif any(w in desc for w in ("saas", "subscription", "aws", "software")):
            cats["software"].append(entry)
        elif any(w in desc for w in ("lunch", "dinner", "cafe", "restaurant")):
            cats["meals"].append(entry)
        else:
            cats["other"].append(entry)
    total = sum(float(t.get("amount", 0)) for t in txs if isinstance(t, dict))
    return {"categories": cats, "summary": {"transaction_count": len(txs), "total_amount": round(total, 2)}}


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()
    if a == "calculate_gst":
        return _calculate_gst(params)
    if a == "generate_invoice":
        return _generate_invoice(params)
    if a == "generate_pnl":
        return _generate_pnl(params)
    if a == "analyze_cashflow":
        return _analyze_cashflow(params)
    if a == "categorize_expenses":
        return _categorize_expenses(params)
    raise ValueError(f"Unknown finance action: {action}")
