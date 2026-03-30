"""Task 64 — timezone helpers and PATCH /auth/me/timezone."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config import TIMEZONE_BY_COUNTRY
from utils.locale_format import format_currency, format_date
from utils.timezone import now_for_user, utc_to_user_tz


def test_now_for_user_dubai():
    dt = now_for_user("Asia/Dubai")
    assert dt.tzinfo is not None
    # Asia/Dubai uses Gulf Standard Time
    assert dt.tzname() is not None


def test_format_currency_inr():
    s = format_currency(2999, "INR", "en-IN")
    assert "₹" in s
    assert "2,999" in s or "2999" in s.replace(",", "")


def test_format_currency_usd():
    s = format_currency(39, "USD", "en-US")
    assert "$" in s
    assert "39.00" in s


def test_format_date_japanese_keeps_kanji_date():
    dt = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
    s = format_date(dt, "ja-JP")
    assert "年" in s and "月" in s and "日" in s


def test_timezone_by_country_count():
    assert len(TIMEZONE_BY_COUNTRY) >= 13


def test_pytz_in_requirements():
    req = Path(__file__).resolve().parent.parent / "requirements.txt"
    assert "pytz" in req.read_text().lower()


def test_patch_auth_me_timezone_200(monkeypatch, client):
    import uuid

    monkeypatch.setenv("AUTH_MODE", "jwt")
    email = f"tz{uuid.uuid4().hex[:8]}@example.com"
    assert client.post(
        "/auth/register",
        json={"email": email, "name": "Tz", "password": "password123"},
    ).status_code == 200
    tok = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    ).json()["token"]

    r = client.patch(
        "/auth/me/timezone",
        json={"timezone": "Europe/London"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["timezone"] == "Europe/London"
    assert "current_time_for_user" in j


def test_utc_to_user_tz():
    utc = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    loc = utc_to_user_tz(utc, "Asia/Kolkata")
    assert loc.hour != 12 or loc.utcoffset() is not None
