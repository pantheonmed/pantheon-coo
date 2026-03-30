"""
tools/security_scanner.py — SSL, headers, password strength, lightweight site checks.
"""
from __future__ import annotations

import re
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from config import settings

_HEADER_NAMES = [
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
]


def _domain_from_url(url: str) -> str:
    p = urlparse(url)
    return (p.hostname or "").strip()


def _check_ssl_sync(domain: str) -> dict[str, Any]:
    d = domain.strip().lower().split(":")[0]
    if not d:
        return {"valid": False, "expiry_date": None, "days_remaining": None, "issuer": None}
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((d, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=d) as ssock:
                cert = ssock.getpeercert()
    except OSError:
        return {"valid": False, "expiry_date": None, "days_remaining": None, "issuer": None}
    if not cert:
        return {"valid": False, "expiry_date": None, "days_remaining": None, "issuer": None}
    not_after = cert.get("notAfter")
    issuer_tup = cert.get("issuer") or ()
    issuer_parts = []
    for part in issuer_tup:
        for k, v in part:
            if k == "organizationName":
                issuer_parts.append(v)
    issuer = ", ".join(issuer_parts) if issuer_parts else str(issuer_tup)
    expiry_date = None
    days_remaining = None
    if not_after:
        expiry_date = not_after
        days_remaining = None
        for fmt in ("%b %d %H:%M:%S %Y GMT", "%b %d %H:%M:%S %Y %Z"):
            try:
                exp = datetime.strptime(not_after, fmt).replace(tzinfo=timezone.utc)
                days_remaining = (exp - datetime.now(timezone.utc)).days
                break
            except ValueError:
                continue
    return {
        "valid": True,
        "expiry_date": expiry_date,
        "days_remaining": days_remaining,
        "issuer": issuer,
    }


def _check_security_headers_sync(url: str) -> dict[str, Any]:
    present: list[str] = []
    missing: list[str] = []
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            r = client.get(url)
        headers = {k.lower(): v for k, v in r.headers.items()}
    except httpx.HTTPError:
        headers = {}
    for h in _HEADER_NAMES:
        if any(h in k for k in headers):
            present.append(h)
        else:
            missing.append(h)
    score = int(round(100 * len(present) / max(len(_HEADER_NAMES), 1)))
    return {"present": present, "missing": missing, "score": score}


def _password_strength_score(pw: str) -> tuple[int, list[str], list[str]]:
    issues: list[str] = []
    suggestions: list[str] = []
    if not pw:
        return 0, ["empty"], ["Use a longer, mixed-character password"]
    score = 0
    if len(pw) >= 8:
        score += 15
    if len(pw) >= 12:
        score += 15
    if len(pw) < 8:
        issues.append("too_short")
        suggestions.append("Use at least 12 characters")
    if re.search(r"[a-z]", pw):
        score += 15
    else:
        issues.append("no_lowercase")
        suggestions.append("Add lowercase letters")
    if re.search(r"[A-Z]", pw):
        score += 15
    else:
        issues.append("no_uppercase")
        suggestions.append("Add uppercase letters")
    if re.search(r"\d", pw):
        score += 15
    else:
        issues.append("no_digit")
        suggestions.append("Add digits")
    if re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\/`~]', pw):
        score += 15
    else:
        issues.append("no_symbol")
        suggestions.append("Add symbols")
    common = {"password", "123456", "qwerty", "letmein", "admin"}
    if pw.lower() in common:
        score = min(score, 20)
        issues.append("common_password")
        suggestions.append("Avoid common passwords")
    if re.search(r"(.)\1{3,}", pw):
        issues.append("repeated_chars")
        score -= 10
    score = max(0, min(100, score))
    return score, issues, suggestions


async def _check_ssl(p: dict[str, Any]) -> dict[str, Any]:
    return _check_ssl_sync(str(p.get("domain", "")))


async def _check_security_headers(p: dict[str, Any]) -> dict[str, Any]:
    return _check_security_headers_sync(str(p.get("url", "")))


async def _check_password_strength(p: dict[str, Any]) -> dict[str, Any]:
    # Never log or persist the password — use only in-memory for scoring.
    password = str(p.get("password", ""))
    score, issues, suggestions = _password_strength_score(password)
    del password
    return {"score": score, "issues": issues, "suggestions": suggestions}


async def _scan_website(p: dict[str, Any]) -> dict[str, Any]:
    url = str(p.get("url", "")).strip()
    checks = [str(x).lower() for x in (p.get("checks") or ["ssl", "headers", "ports"])]
    domain = _domain_from_url(url)
    ssl_info = (
        _check_ssl_sync(domain)
        if domain and "ssl" in checks
        else {"valid": False, "expiry_date": None, "days_remaining": None, "issuer": None}
    )
    headers_info = _check_security_headers_sync(url) if "headers" in checks else {"present": [], "missing": _HEADER_NAMES, "score": 0}
    vulnerabilities: list[str] = []
    recommendations: list[str] = []
    if not ssl_info.get("valid"):
        vulnerabilities.append("SSL handshake failed or no certificate")
        recommendations.append("Enable valid TLS 1.2+ and renew certificates")
    dr = ssl_info.get("days_remaining")
    if isinstance(dr, int) and dr < 30:
        vulnerabilities.append("SSL certificate expiring within 30 days")
        recommendations.append("Renew TLS certificate before expiry")
    for m in headers_info.get("missing", []):
        if m == "strict-transport-security":
            vulnerabilities.append("Missing HSTS header")
            recommendations.append("Add Strict-Transport-Security")
        elif m == "content-security-policy":
            vulnerabilities.append("Missing Content-Security-Policy")
            recommendations.append("Add a strict CSP")
    sec_headers = {"present": headers_info.get("present", []), "missing": headers_info.get("missing", [])}
    hdr_score = headers_info.get("score", 0)
    ssl_score = 50 if ssl_info.get("valid") else 0
    if isinstance(dr, int) and dr > 30:
        ssl_score = 50
    elif isinstance(dr, int) and dr > 0:
        ssl_score = 35
    security_score = max(0, min(100, int((ssl_score + hdr_score) / 2)))
    return {
        "url": url,
        "ssl_valid": bool(ssl_info.get("valid")),
        "ssl_expiry": ssl_info.get("expiry_date"),
        "security_headers": sec_headers,
        "vulnerabilities": vulnerabilities,
        "security_score": security_score,
        "recommendations": recommendations,
    }


async def _generate_security_report(p: dict[str, Any]) -> dict[str, Any]:
    target = str(p.get("target_url", "")).strip()
    scan = await _scan_website({"url": target, "checks": ["ssl", "headers"]})
    domain = _domain_from_url(target) or "unknown"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", domain)[:80]
    out_dir = Path(settings.workspace_dir).resolve() / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{safe}.md"
    lines = [
        f"# Security report: {target}",
        "",
        f"Score: {scan.get('security_score')}/100",
        "",
        "## SSL",
        f"- Valid: {scan.get('ssl_valid')}",
        f"- Expiry: {scan.get('ssl_expiry')}",
        "",
        "## Headers",
        f"- Present: {scan.get('security_headers', {}).get('present')}",
        f"- Missing: {scan.get('security_headers', {}).get('missing')}",
        "",
        "## Findings",
        *[f"- {v}" for v in scan.get("vulnerabilities", [])],
        "",
        "## Recommendations",
        *[f"- {r}" for r in scan.get("recommendations", [])],
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"report_path": str(path), **scan}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "scan_website": _scan_website,
        "check_ssl": _check_ssl,
        "check_security_headers": _check_security_headers,
        "check_password_strength": _check_password_strength,
        "generate_security_report": _generate_security_report,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown security_scanner action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
