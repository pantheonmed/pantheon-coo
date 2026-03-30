"""Locale-aware currency, number, and date formatting (lightweight, no Babel)."""
from __future__ import annotations

from datetime import datetime


def _group_in(n: int, group_size: int = 3) -> str:
    s = str(abs(int(n)))
    if group_size == 3:
        parts = []
        while s:
            parts.append(s[-3:])
            s = s[:-3]
        out = ",".join(reversed(parts))
    else:
        # Indian: last 3 then groups of 2
        if len(s) <= 3:
            out = s
        else:
            last3 = s[-3:]
            rest = s[:-3]
            parts2 = []
            while rest:
                parts2.append(rest[-2:])
                rest = rest[:-2]
            out = ",".join(reversed(parts2)) + "," + last3
    return ("-" if n < 0 else "") + out


def format_number(n: float, loc: str) -> str:
    """Format integers/part counts; Indian vs Western grouping."""
    if abs(n - int(n)) < 1e-9:
        v = int(round(n))
    else:
        v = n
    loc_l = (loc or "en-US").replace("_", "-").lower()
    if loc_l in ("en-in", "hi-in", "ta-in") or loc.startswith("en-IN"):
        if isinstance(v, int):
            return _group_in(v, 2)
        return f"{v:.2f}"
    if isinstance(v, float):
        dec = abs(v - int(v)) < 1e-9
        if dec:
            return _group_in(int(round(v)), 3)
        whole, frac = f"{v:.6f}".split(".")
        return _group_in(int(whole), 3) + "." + frac.rstrip("0").rstrip(".")[:2]
    return _group_in(int(v), 3)


def format_currency(amount: float, currency: str, loc: str) -> str:
    c = (currency or "USD").upper()
    loc_l = (loc or "en-US").replace("_", "-")

    if c == "INR" and ("IN" in loc_l.upper() or loc_l.lower() in ("hi-in", "ta-in")):
        if abs(amount - int(amount)) < 1e-6:
            n = int(round(amount))
            return "₹" + _group_in(n, 2)
        return "₹" + f"{amount:,.2f}"
    if c == "USD" and loc_l.upper().startswith("EN-US"):
        return f"${amount:,.2f}"
    if c == "EUR" and loc_l.upper().startswith("DE"):
        return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"
    if c == "EUR":
        return f"€{amount:,.2f}"
    if c == "AED" and "AR" in loc_l.upper():
        s = f"{amount:,.2f}"
        s = s.replace(",", "٬").replace(".", "٫")
        return s + " د.إ"
    if c == "AED":
        return f"AED {amount:,.2f}"
    if c == "JPY" or loc_l.upper().startswith("JA"):
        return f"¥{int(round(amount)):,}"
    sym = {"GBP": "£", "BRL": "R$", "IDR": "Rp", "SGD": "S$", "NGN": "₦"}.get(c, "")
    if sym:
        return f"{sym}{amount:,.2f}"
    return f"{amount:,.2f} {c}"


_MONTH_NAMES = {
    "de": (
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
}


def format_date(dt: datetime, loc: str) -> str:
    loc_l = (loc or "en-IN").replace("_", "-")
    if loc_l.lower() == "ja-jp" or loc.upper().startswith("JA"):
        return f"{dt.year}年{dt.month}月{dt.day}日"
    if loc_l.lower() == "ar-ae" or loc.upper().startswith("AR-AE"):
        # Eastern Arabic numerals for test expectation
        trans = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
        months = (
            "",
            "يناير",
            "فبراير",
            "مارس",
            "أبريل",
            "مايو",
            "يونيو",
            "يوليو",
            "أغسطس",
            "سبتمبر",
            "أكتوبر",
            "نوفمبر",
            "ديسمبر",
        )
        d, m, y = dt.day, dt.month, dt.year
        return f"{str(d).translate(trans)} {months[m]} {str(y).translate(trans)}"
    if loc_l.lower().startswith("de-de"):
        months = _MONTH_NAMES["de"]
        return f"{dt.day}. {months[dt.month]} {dt.year}"
    if loc_l.lower().startswith("en-us"):
        mo = dt.strftime("%b")
        return f"{mo} {dt.day}, {dt.year}"
    # en-IN default
    mo = dt.strftime("%b")
    return f"{dt.day} {mo} {dt.year}"


__all__ = ["format_currency", "format_number", "format_date"]
