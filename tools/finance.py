"""
tools/finance.py — GST, invoices, P&L, cashflow, expense categories (pure Python).
"""
from __future__ import annotations

import re
import time
from datetime import datetime
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
    p = dict(p or {})
    if p.get("client_name") and not p.get("buyer_name"):
        p["buyer_name"] = str(p["client_name"])
    if p.get("client_address") and not p.get("buyer_address"):
        p["buyer_address"] = str(p["client_address"])
    if p.get("invoice_no") and not p.get("invoice_number"):
        p["invoice_number"] = str(p["invoice_no"])
    items = list(p.get("items") or [])
    if not items and (p.get("amount") is not None or p.get("product_service")):
        amt = float(p.get("amount") or 0)
        gst_r = int(float(p.get("gst_rate") or 18))
        desc = str(p.get("product_service") or "Services")
        items = [{"description": desc, "qty": 1, "rate": amt, "gst_rate": gst_r}]

    if not items:
        raise ValueError("generate_invoice requires items or amount/product_service for a line item.")

    company_name = str(p.get("company_name") or p.get("seller_name") or "Pantheon Meditech Pvt Ltd")
    company_gstin = str(p.get("company_gstin") or p.get("seller_gstin") or "")
    seller_address = str(p.get("seller_address") or "Salem, Tamil Nadu - 636001")

    inv_dir = _ws_root() / "invoices"
    inv_dir.mkdir(parents=True, exist_ok=True)
    num = str(p.get("invoice_number") or f"INV-{int(time.time())}")
    invoice_date = str(p.get("invoice_date") or datetime.now().strftime("%d %B %Y"))
    due_date = str(p.get("due_date") or "")

    subtotal = 0.0
    gst_rate = int(_validate_gst_rate(items[0].get("gst_rate", 18)))
    items_html = ""
    for i, it in enumerate(items, 1):
        desc = str(it.get("description", ""))
        qty = float(it.get("qty", 1))
        rate = float(it.get("rate", 0))
        gst_r = int(_validate_gst_rate(it.get("gst_rate", gst_rate)))
        line = qty * rate
        subtotal += line
        items_html += f"""
        <tr>
            <td>{i}</td>
            <td>{desc}</td>
            <td>{qty}</td>
            <td>₹{rate:,.2f}</td>
            <td>₹{line:,.2f}</td>
        </tr>"""

    cgst = subtotal * (gst_rate / 2) / 100.0
    sgst = subtotal * (gst_rate / 2) / 100.0
    tax_total = cgst + sgst
    total = subtotal + tax_total

    buyer_name = str(p.get("buyer_name") or "")
    buyer_addr = str(p.get("buyer_address") or "")
    buyer_gstin = str(p.get("buyer_gstin") or "")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
  .header {{ display: flex; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
  .company {{ font-size: 24px; font-weight: bold; color: #7c6ff7; }}
  table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
  th {{ background: #7c6ff7; color: white; padding: 10px; }}
  td {{ padding: 8px; border: 1px solid #ddd; }}
  .total {{ font-size: 20px; font-weight: bold; color: #7c6ff7; }}
  .gst-box {{ background: #f9f9f9; padding: 16px; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="company">{company_name}</div>
    <div>GSTIN: {company_gstin}</div>
    <div>{seller_address}</div>
  </div>
  <div style="text-align:right">
    <div style="font-size:20px"><strong>TAX INVOICE</strong></div>
    <div>Invoice #: {num}</div>
    <div>Date: {invoice_date}</div>
    {f'<div>Due: {due_date}</div>' if due_date else ''}
  </div>
</div>

<hr>

<div style="margin: 20px 0">
  <strong>Bill To:</strong><br>
  {buyer_name}
  {f'<br>GSTIN: {buyer_gstin}' if buyer_gstin else ''}<br>
  {buyer_addr.replace(chr(10), '<br>')}
</div>

<table>
  <thead>
    <tr>
      <th>#</th>
      <th>Description</th>
      <th>Qty</th>
      <th>Rate</th>
      <th>Amount</th>
    </tr>
  </thead>
  <tbody>
    {items_html}
  </tbody>
</table>

<div class="gst-box" style="text-align:right">
  <div>Subtotal: ₹{subtotal:,.2f}</div>
  <div>CGST ({gst_rate/2}%): ₹{cgst:,.2f}</div>
  <div>SGST ({gst_rate/2}%): ₹{sgst:,.2f}</div>
  <div class="total">Total: ₹{total:,.2f}</div>
</div>

<div style="margin-top:40px;color:#888;font-size:12px">
  This is a computer generated invoice.
  Powered by Pantheon COO OS — trycooai.com
</div>
</body>
</html>"""

    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", num)[:60]
    html_file = inv_dir / f"{safe}.html"
    txt_file = inv_dir / f"{safe}.txt"
    html_file.write_text(html, encoding="utf-8")
    txt_file.write_text(
        f"Invoice: {num}\nClient: {buyer_name}\nTotal: ₹{total:,.2f}\nCGST: ₹{cgst:,.2f}\nSGST: ₹{sgst:,.2f}\n",
        encoding="utf-8",
    )
    return {
        "invoice_number": num,
        "html_file": str(html_file),
        "txt_file": str(txt_file),
        "file_path": str(html_file),
        "subtotal": round(subtotal, 2),
        "cgst": round(cgst, 2),
        "sgst": round(sgst, 2),
        "total": round(total, 2),
        "total_amount": round(total, 2),
        "tax_amount": round(tax_total, 2),
        "success": True,
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
