"""Task 50 — Google Calendar tool."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import ToolName
from tools import google_calendar as cal_mod


@pytest.mark.asyncio
async def test_create_event_request_format():
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None, params=None):
            captured["json"] = json
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(
                return_value={
                    "id": "ev1",
                    "htmlLink": "https://calendar.google.com/e",
                    "conferenceData": {},
                }
            )
            return resp

    with (
        patch("tools.google_calendar._token", new_callable=AsyncMock, return_value="t"),
        patch("tools.google_calendar.httpx.AsyncClient", return_value=FakeClient()),
    ):
        await cal_mod.execute(
            "create_event",
            {
                "title": "Sync",
                "start_datetime": "2026-03-30T10:00:00+05:30",
                "end_datetime": "2026-03-30T11:00:00+05:30",
                "meet_link": False,
            },
        )
    assert captured["json"]["summary"] == "Sync"


@pytest.mark.asyncio
async def test_get_events_returns_title():
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None, params=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(
                return_value={
                    "items": [
                        {
                            "summary": "Meet",
                            "start": {"dateTime": "2026-01-01T09:00:00Z"},
                            "end": {"dateTime": "2026-01-01T10:00:00Z"},
                            "attendees": [],
                        }
                    ]
                }
            )
            return resp

    with (
        patch("tools.google_calendar._token", new_callable=AsyncMock, return_value="t"),
        patch("tools.google_calendar.httpx.AsyncClient", return_value=FakeClient()),
    ):
        evs = await cal_mod.execute(
            "get_events",
            {
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-01-31T23:59:59Z",
            },
        )
    assert evs[0]["title"] == "Meet"


@pytest.mark.asyncio
async def test_find_free_slot_returns_slots():
    slots = await cal_mod.execute(
        "find_free_slot",
        {
            "duration_minutes": 30,
            "preferred_dates": ["2026-04-01", "2026-04-02"],
            "working_hours": {"start": "09:00", "end": "12:00"},
        },
    )
    assert isinstance(slots, list)
    assert len(slots) >= 1
    assert "start" in slots[0]


def test_toolname_google_calendar_enum():
    assert ToolName.GOOGLE_CALENDAR.value == "google_calendar"
