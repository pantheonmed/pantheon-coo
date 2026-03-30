"""
tools/compliance.py — GSTIN/PAN validation, compliance checklists, NDA/MOU templates.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config import settings

_LEGAL_DISCLAIMER = (
    "DISCLAIMER: This is a template for reference only. "
    "Consult a qualified legal professional before use."
)

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum_char(code_14: str) -> str:
    factor = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    summation = 0
    for i in range(14):
        codepoint = _GSTIN_CHARS.index(code_14[i].upper())
        prod = codepoint * factor[i]
        summation += (prod // 36) + (prod % 36)
    check = (36 - (summation % 36)) % 36
    return _GSTIN_CHARS[check]


def _validate_gstin_core(gstin: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    g = (gstin or "").strip().upper()
    if len(g) != 15:
        errors.append("GSTIN must be exactly 15 characters.")
        return False, errors
    if not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]Z[0-9A-Z]$", g):
        errors.append("GSTIN structure is invalid.")
        return False, errors
    if g[13] != "Z":
        errors.append("14th character must be Z.")
    expected = _gstin_checksum_char(g[:14])
    if g[14] != expected:
        errors.append(f"Checksum mismatch (expected {expected}).")
    if errors:
        return False, errors
    return True, []


def _gst_entity_type(code: str) -> str:
    m = {
        "1": "Others",
        "2": "Company",
        "3": "Others",
        "4": "Partnership",
        "5": "Proprietorship",
        "6": "Others",
        "7": "Government",
        "8": "Others",
        "9": "Others",
    }
    return m.get(code.upper(), "Unknown")


def _pan_entity_type(fifth: str) -> str:
    m = {
        "P": "Individual",
        "C": "Company",
        "H": "HUF",
        "F": "Firm",
        "A": "Association of persons",
        "T": "Trust",
        "B": "Body of individuals",
        "L": "Local authority",
        "J": "Artificial juridical person",
        "G": "Government",
    }
    return m.get(fifth.upper(), "Unknown")


def _state_name_from_code(code: str) -> str:
    # Minimal mapping for PAN fourth char context (placeholder)
    return f"region_code_{code}"


def gst_compliance_check(p: dict[str, Any]) -> dict[str, Any]:
    gstin = str(p.get("gstin", "")).strip().upper()
    valid, _ = _validate_gstin_core(gstin)
    state_code = gstin[:2] if len(gstin) >= 2 else ""
    pan = gstin[2:12] if len(gstin) >= 12 else ""
    entity = gstin[12] if len(gstin) > 12 else ""
    return {
        "valid": valid,
        "state_code": state_code,
        "entity_type": _gst_entity_type(entity),
        "pan": pan,
    }


def validate_gstin(p: dict[str, Any]) -> dict[str, Any]:
    gstin = str(p.get("gstin", "")).strip()
    ok, errors = _validate_gstin_core(gstin)
    return {"valid": ok, "errors": errors}


def validate_pan(p: dict[str, Any]) -> dict[str, Any]:
    pan = str(p.get("pan", "")).strip().upper()
    ok = bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan))
    # 4th character (1-based) encodes holder type per Indian PAN rules.
    fourth = pan[3] if len(pan) >= 4 else ""
    first = pan[0] if len(pan) >= 1 else ""
    return {
        "valid": ok,
        "entity_type": _pan_entity_type(fourth) if ok else "",
        "state": _state_name_from_code(first) if ok else "",
    }


def generate_compliance_doc(p: dict[str, Any]) -> dict[str, Any]:
    regulation = str(p.get("regulation") or "").upper()
    company = str(p.get("company_name", ""))
    product = str(p.get("product_name", ""))
    out_dir = Path(settings.workspace_dir).resolve() / "compliance"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", regulation.lower())[:40]
    path = out_dir / f"compliance_{safe}.md"
    sections = {
        "CDSCO": [
            "Device classification and intended use",
            "Risk management file (ISO 14971)",
            "Clinical evaluation / equivalence",
            "Labelling and IFU",
            "Post-market surveillance plan",
        ],
        "ISO13485": [
            "Quality manual and QMS scope",
            "Management responsibility",
            "Design and development controls",
            "CAPA and nonconformance",
            "Internal audit program",
        ],
        "MDR2017": [
            "Registration with CDSCO where applicable",
            "Conformity to essential principles",
            "Importer / manufacturer obligations",
            "Complaint handling and vigilance",
        ],
        "GDPR": [
            "Lawful basis and consent records",
            "Data subject rights process",
            "DPIA for high-risk processing",
            "Processor agreements",
            "Breach notification procedure",
        ],
        "SOC2": [
            "Control environment documentation",
            "Access control and MFA",
            "Change management",
            "Logging and monitoring",
            "Vendor management",
        ],
    }
    checklist = sections.get(regulation, ["General compliance review", "Documentation", "Training", "Audit"])
    body = "\n".join(f"- [ ] {c}" for c in checklist)
    md = (
        f"# Compliance checklist — {regulation}\n\n"
        f"**Company:** {company}\n**Product / scope:** {product}\n\n"
        f"{body}\n\n{_LEGAL_DISCLAIMER}\n"
    )
    path.write_text(md, encoding="utf-8")
    return {"file_path": str(path), "regulation": regulation}


def create_nda(p: dict[str, Any]) -> dict[str, Any]:
    p1n = str(p.get("party1_name", ""))
    p1a = str(p.get("party1_address", ""))
    p2n = str(p.get("party2_name", ""))
    p2a = str(p.get("party2_address", ""))
    purpose = str(p.get("purpose", ""))
    years = int(p.get("duration_years") or 2)
    out_dir = Path(settings.workspace_dir).resolve() / "legal"
    out_dir.mkdir(parents=True, exist_ok=True)
    s1 = re.sub(r"[^a-zA-Z0-9_-]+", "_", p1n)[:30]
    s2 = re.sub(r"[^a-zA-Z0-9_-]+", "_", p2n)[:30]
    path = out_dir / f"nda_{s1}_{s2}.md"
    md = f"""# Mutual Non-Disclosure Agreement

Between **{p1n}** ({p1a}) and **{p2n}** ({p2a}).

**Purpose:** {purpose}

**Term:** {years} years from the effective date.

1. Confidential Information means non-public information disclosed in connection with the purpose above.
2. Receiving party shall use the same care as with its own confidential information, but no less than reasonable care.
3. Exclusions: public domain, independently developed, rightfully received from third parties, or legally compelled disclosure.
4. Return or destruction of materials upon request.

{_LEGAL_DISCLAIMER}
"""
    path.write_text(md, encoding="utf-8")
    return {"file_path": str(path)}


def create_mou(p: dict[str, Any]) -> dict[str, Any]:
    party1 = p.get("party1") or {}
    party2 = p.get("party2") or {}
    purpose = str(p.get("purpose", ""))
    terms = p.get("terms") or []
    duration = str(p.get("duration", ""))
    out_dir = Path(settings.workspace_dir).resolve() / "legal"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "mou_template.md"
    tlines = "\n".join(f"{i+1}. {t}" for i, t in enumerate(terms)) if terms else "1. (Add specific terms)"
    md = f"""# Memorandum of Understanding

**Party A:** {party1}

**Party B:** {party2}

**Purpose:** {purpose}

**Duration:** {duration}

**Terms:**
{tlines}

{_LEGAL_DISCLAIMER}
"""
    path.write_text(md, encoding="utf-8")
    return {"file_path": str(path)}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "gst_compliance_check": gst_compliance_check,
        "generate_compliance_doc": generate_compliance_doc,
        "create_nda": create_nda,
        "create_mou": create_mou,
        "validate_pan": validate_pan,
        "validate_gstin": validate_gstin,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown compliance action: '{action}'. Available: {list(dispatch)}")
    return fn(params)
