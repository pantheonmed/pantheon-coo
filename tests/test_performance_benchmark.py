"""Lightweight performance smoke checks (Task 92)."""
from __future__ import annotations

import time

import pytest


class TestPerformanceBenchmarks:
    def test_health_under_budget(self, client):
        start = time.monotonic()
        client.get("/health")
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 3000, f"health too slow: {elapsed_ms:.0f}ms"

    def test_tasks_list_under_budget(self, client):
        start = time.monotonic()
        client.get("/tasks")
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 3000, f"/tasks too slow: {elapsed_ms:.0f}ms"

    def test_concurrent_execute_accepted(self, client):
        import concurrent.futures

        def submit():
            return client.post(
                "/execute",
                json={"command": "check disk space and save report to workspace"},
            )

        with concurrent.futures.ThreadPoolExecutor(5) as ex:
            results = list(ex.map(lambda _: submit(), range(5)))
        codes = [r.status_code for r in results]
        assert all(c in (202, 429) for c in codes)
