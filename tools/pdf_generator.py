"""
tools/pdf_generator.py — PDFs via reportlab (invoice, report, letter, markdown).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings


def _pdf_dir() -> Path:
    d = Path(settings.workspace_dir).resolve() / "pdfs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_ws_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    ws = Path(settings.workspace_dir).resolve()
    try:
        p.relative_to(ws)
    except ValueError:
        raise ValueError("markdown_file_path must be under workspace_dir")
    return p


def _create_invoice_pdf(p: dict[str, Any]) -> dict[str, Any]:
    data = p.get("invoice_data") or p
    num = str(data.get("invoice_number") or data.get("number") or "INV1")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", num)[:60]
    path = _pdf_dir() / f"invoice_{safe}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("<b>Tax Invoice</b>", styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))
    seller = data.get("seller_name", "")
    buyer = data.get("buyer_name", "")
    story.append(Paragraph(f"<b>Seller:</b> {seller} — GSTIN {data.get('seller_gstin','')}", styles["Normal"]))
    story.append(Paragraph(str(data.get("seller_address", "")), styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"<b>Buyer:</b> {buyer} — GSTIN {data.get('buyer_gstin','')}", styles["Normal"]))
    story.append(Paragraph(str(data.get("buyer_address", "")), styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            f"Invoice #{num} &nbsp; Date {data.get('invoice_date','')} &nbsp; Due {data.get('due_date','')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    items = data.get("items") or []
    table_data = [["Item", "Qty", "Rate", "GST%", "Line total"]]
    subtotal = 0.0
    tax_total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("description", ""))
        qty = float(it.get("qty", 1))
        rate = float(it.get("rate", 0))
        gst_r = float(it.get("gst_rate", 18))
        line = qty * rate
        tax = line * gst_r / 100.0
        subtotal += line
        tax_total += tax
        table_data.append([desc, f"{qty}", f"{rate}", f"{gst_r}%", f"{line + tax:.2f}"])
    grand = subtotal + tax_total
    table_data.append(["", "", "", "Subtotal", f"{subtotal:.2f}"])
    table_data.append(["", "", "", "Tax", f"{tax_total:.2f}"])
    table_data.append(["", "", "", "<b>Grand</b>", f"<b>{grand:.2f}</b>"])
    t = Table(table_data, colWidths=[6 * cm, 2 * cm, 2 * cm, 2 * cm, 3 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), "#cccccc"),
                ("GRID", (0, 0), (-1, -1), 0.5, "#333333"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(t)
    doc.build(story)
    return {"pdf_path": str(path), "file_size_bytes": path.stat().st_size}


def _create_report_pdf(p: dict[str, Any]) -> dict[str, Any]:
    title = str(p.get("title") or "Report")
    sections = p.get("sections") or []
    footer_text = str(p.get("footer_text") or "Pantheon COO OS")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", title)[:50]
    path = _pdf_dir() / f"report_{safe}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    styles = getSampleStyleSheet()
    h2 = ParagraphStyle(name="H2", parent=styles["Heading2"], spaceAfter=8)
    story = []
    story.append(Paragraph(title.replace("&", "&amp;"), styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))
    pages_hint = 1
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        heading = str(sec.get("heading", ""))
        content = str(sec.get("content", ""))
        story.append(Paragraph(heading.replace("&", "&amp;"), h2))
        for para in content.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.replace("&", "&amp;").replace("<", "&lt;"), styles["Normal"]))
        td = sec.get("table_data")
        if td and isinstance(td, (list, tuple)) and len(td) > 0:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Table(list(td)))
        story.append(Spacer(1, 0.4 * cm))
        pages_hint += 1
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(f"<i>{footer_text.replace('&', '&amp;')}</i>", styles["Normal"]))
    doc.build(story)
    return {"pdf_path": str(path), "pages": max(1, pages_hint)}


def _create_letter_pdf(p: dict[str, Any]) -> dict[str, Any]:
    safe = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        (p.get("subject") or "letter")[:40],
    )
    path = _pdf_dir() / f"letter_{safe}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(str(p.get("date", "")), styles["Normal"]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(f"<b>{p.get('from_name','')}</b><br/>{p.get('from_address','')}", styles["Normal"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"<b>{p.get('to_name','')}</b><br/>{p.get('to_address','')}", styles["Normal"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"<b>Subject:</b> {p.get('subject','')}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))
    body = str(p.get("body", ""))
    for para in body.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.replace("&", "&amp;").replace("<", "&lt;"), styles["Normal"]))
    doc.build(story)
    return {"pdf_path": str(path)}


def _markdown_to_pdf(p: dict[str, Any]) -> dict[str, Any]:
    md_path = _validate_ws_path(str(p.get("markdown_file_path", "")))
    if md_path.suffix.lower() not in (".md", ".markdown"):
        raise ValueError("File must be a .md markdown file.")
    text = md_path.read_text(encoding="utf-8", errors="replace")
    stem = md_path.stem
    path = _pdf_dir() / f"{stem}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []
    for block in re.split(r"\n{2,}", text):
        line = block.strip()
        if not line:
            continue
        if line.startswith("#"):
            story.append(Paragraph(line.lstrip("# ").replace("&", "&amp;"), styles["Heading2"]))
        else:
            story.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), styles["Normal"]))
        story.append(Spacer(1, 0.2 * cm))
    doc.build(story)
    return {"pdf_path": str(path)}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    if act == "create_invoice_pdf":
        return _create_invoice_pdf(params)
    if act == "create_report_pdf":
        return _create_report_pdf(params)
    if act == "create_letter_pdf":
        return _create_letter_pdf(params)
    if act == "markdown_to_pdf":
        return _markdown_to_pdf(params)
    raise ValueError(
        f"Unknown pdf_generator action: '{action}'. "
        "Available: create_invoice_pdf, create_report_pdf, create_letter_pdf, markdown_to_pdf"
    )
