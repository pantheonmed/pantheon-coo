"""Task 43 — security scanner + sandbox."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import security_scanner as sec_mod


def _patch_scan_sync():
    return patch.multiple(
        sec_mod,
        _check_ssl_sync=MagicMock(
            return_value={
                "valid": True,
                "expiry_date": "Jan 1 2030 GMT",
                "days_remaining": 200,
                "issuer": "CA",
            }
        ),
        _check_security_headers_sync=MagicMock(
            return_value={
                "present": ["strict-transport-security"],
                "missing": [
                    "content-security-policy",
                    "x-frame-options",
                    "x-content-type-options",
                    "referrer-policy",
                ],
                "score": 20,
            }
        ),
    )


@pytest.mark.asyncio
async def test_scan_website_security_score():
    with _patch_scan_sync():
        r = await sec_mod.execute(
            "scan_website",
            {"url": "https://example.com", "checks": ["ssl", "headers"]},
        )
    assert "security_score" in r
    assert isinstance(r["security_score"], int)


@pytest.mark.asyncio
async def test_check_ssl_days_remaining():
    with patch.object(
        sec_mod,
        "_check_ssl_sync",
        return_value={
            "valid": True,
            "expiry_date": "Jan 1 2030 GMT",
            "days_remaining": 400,
            "issuer": "CA",
        },
    ):
        r = await sec_mod.execute("check_ssl", {"domain": "example.com"})
    assert r.get("days_remaining") == 400


def test_localhost_scan_blocked():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.SECURITY_SCANNER,
        action="scan_website",
        params={"url": "http://127.0.0.1/"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError):
        validate_step(step)


@pytest.mark.asyncio
async def test_weak_password_score():
    r = await sec_mod.execute("check_password_strength", {"password": "123456"})
    assert r["score"] < 30


@pytest.mark.asyncio
async def test_strong_password_score():
    r = await sec_mod.execute("check_password_strength", {"password": "P@ssw0rd#2026!"})
    assert r["score"] > 70


def test_toolname_security_scanner_enum():
    assert ToolName.SECURITY_SCANNER.value == "security_scanner"
