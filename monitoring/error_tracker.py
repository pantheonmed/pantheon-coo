"""
monitoring/error_tracker.py — in-process error log + optional admin alerts.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("pantheon.errors")

CRITICAL_ERRORS = frozenset(
    {
        "DatabaseError",
        "OperationalError",
        "AuthenticationError",
        "AuthError",
        "PaymentError",
        "CardError",
        "InvalidRequestError",
        "APIError",
        "APIStatusError",
        "RateLimitError",
        "AnthropicError",
    }
)

_alert_count_today: int = 0
_alert_day: str = ""


def _bump_alert_count() -> None:
    global _alert_count_today, _alert_day
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if day != _alert_day:
        _alert_day = day
        _alert_count_today = 0
    _alert_count_today += 1


class ErrorTracker:
    def __init__(self) -> None:
        self._errors: list[dict[str, Any]] = []
        self._alerts_sent: set[str] = set()
        self._lock = asyncio.Lock()

    async def track(
        self,
        error: BaseException,
        context: dict | None = None,
        user_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        ctx = dict(context or {})
        et = type(error).__name__
        error_record: dict[str, Any] = {
            "id": str(uuid.uuid4())[:8],
            "type": et,
            "message": str(error),
            "context": ctx,
            "user_id": user_id or "",
            "task_id": task_id or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._errors.append(error_record)
            if len(self._errors) > 500:
                self._errors = self._errors[-400:]

        log.error(
            "%s: %s",
            error_record["type"],
            error_record["message"],
            extra={"error_id": error_record["id"]},
        )

        if et in CRITICAL_ERRORS:
            await self._send_alert(error_record)
        return error_record

    async def _send_alert(self, error: dict[str, Any]) -> None:
        key = f"{error['type']}:{error['message'][:80]}"
        if key in self._alerts_sent:
            return
        self._alerts_sent.add(key)
        if len(self._alerts_sent) > 200:
            self._alerts_sent = set(list(self._alerts_sent)[-100:])
        _bump_alert_count()
        try:
            from config import settings

            if (settings.admin_email or "").strip():
                log.warning(
                    "[alert] critical error id=%s type=%s",
                    error.get("id"),
                    error.get("type"),
                )
        except Exception:
            pass

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 200))
        return list(self._errors[-lim:])

    def error_count_last_hour(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        n = 0
        for e in self._errors:
            try:
                ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    n += 1
            except Exception:
                continue
        return n


_tracker = ErrorTracker()


async def track_error(
    error: BaseException,
    *,
    context: dict | None = None,
    user_id: str = "",
    task_id: str = "",
) -> None:
    await _tracker.track(error, context=context, user_id=user_id, task_id=task_id)


def get_tracker() -> ErrorTracker:
    return _tracker


def get_alert_count_today() -> int:
    global _alert_day, _alert_count_today
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if day != _alert_day:
        return 0
    return _alert_count_today
