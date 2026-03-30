#!/usr/bin/env python3
"""
healthcheck.py
──────────────
Validates a running Pantheon COO OS deployment.

Usage:
  python3 healthcheck.py                           # check localhost:8002
  python3 healthcheck.py --url http://my-server:8002
  python3 healthcheck.py --url http://localhost:8002 --key your-api-key

Exit codes:
  0 — all checks passed
  1 — one or more checks failed
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Check result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

def _request(
    url: str,
    method: str = "GET",
    body: Optional[dict] = None,
    api_key: str = "",
    timeout: int = 10,
) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("X-COO-API-Key", api_key)

    data = None
    if body:
        data = json.dumps(body).encode()

    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = str(e)
        return e.code, detail
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot reach {url}: {e.reason}")


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def check_health(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/health", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200 and isinstance(data, dict) and data.get("status") == "ok":
            agents = data.get("agents", [])
            phases = data.get("phases_active", [])
            return Check(
                "Health endpoint",
                passed=True,
                detail=f"{len(agents)} agents, {len(phases)} phases active",
                duration_ms=ms,
            )
        return Check("Health endpoint", passed=False,
                     detail=f"HTTP {status}: {data}", duration_ms=ms)
    except ConnectionError as e:
        return Check("Health endpoint", passed=False, detail=str(e))


def check_stats(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/stats", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200 and isinstance(data, dict):
            total = data.get("total", 0)
            learnings = data.get("learnings", 0)
            return Check("Stats endpoint", passed=True,
                         detail=f"{total} tasks, {learnings} learnings in DB",
                         duration_ms=ms)
        return Check("Stats endpoint", passed=False,
                     detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Stats endpoint", passed=False, detail=str(e))


def check_model_router(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/monitor/model-status", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200 and isinstance(data, dict):
            circuit = data.get("claude_circuit", "unknown")
            model = data.get("primary_model", "unknown")
            degraded = "open" in circuit
            return Check(
                "Model router",
                passed=True,
                detail=f"Primary: {model} | Circuit: {circuit}",
                duration_ms=ms,
            )
        return Check("Model router", passed=False,
                     detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Model router", passed=False, detail=str(e))


def check_execute_endpoint(base: str, key: str) -> Check:
    """Submit a dry-run command and verify a task_id is returned."""
    t0 = time.monotonic()
    try:
        status, data = _request(
            f"{base}/execute",
            method="POST",
            body={"command": "healthcheck: list workspace files", "dry_run": True},
            api_key=key,
        )
        ms = (time.monotonic() - t0) * 1000
        if status == 202 and isinstance(data, dict) and "task_id" in data:
            task_id = data["task_id"][:8]
            return Check("Execute endpoint (dry run)", passed=True,
                         detail=f"Task {task_id} queued",
                         duration_ms=ms)
        if status in (401, 403):
            return Check("Execute endpoint (dry run)", passed=False,
                         detail="Auth failed — check COO_API_KEY",
                         duration_ms=ms)
        return Check("Execute endpoint (dry run)", passed=False,
                     detail=f"HTTP {status}: {data}",
                     duration_ms=ms)
    except Exception as e:
        return Check("Execute endpoint (dry run)", passed=False, detail=str(e))


def check_memory(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/memory/learnings?limit=1", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200:
            count = len(data.get("learnings", [])) if isinstance(data, dict) else 0
            return Check("Memory / learnings", passed=True,
                         detail=f"Endpoint reachable ({count} learnings returned)",
                         duration_ms=ms)
        return Check("Memory / learnings", passed=False,
                     detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Memory / learnings", passed=False, detail=str(e))


def check_schedules(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/schedules", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200:
            count = len(data.get("schedules", [])) if isinstance(data, dict) else 0
            return Check("Scheduler", passed=True,
                         detail=f"{count} active schedule(s)",
                         duration_ms=ms)
        return Check("Scheduler", passed=False, detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Scheduler", passed=False, detail=str(e))


def check_projects(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/projects", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200:
            count = len(data.get("projects", [])) if isinstance(data, dict) else 0
            return Check("Projects API", passed=True,
                         detail=f"{count} project(s) tracked",
                         duration_ms=ms)
        return Check("Projects API", passed=False, detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Projects API", passed=False, detail=str(e))


def check_monitor_metrics(base: str, key: str) -> Check:
    t0 = time.monotonic()
    try:
        status, data = _request(f"{base}/monitor/metrics?hours=24", api_key=key)
        ms = (time.monotonic() - t0) * 1000
        if status == 200 and isinstance(data, dict):
            health = data.get("health", "unknown")
            alerts = data.get("alerts", [])
            total = data.get("totals", {}).get("tasks", 0)
            avg = data.get("performance", {}).get("avg_eval_score")
            score_str = f", avg score {avg:.2f}" if avg else ""
            alert_str = f" [{len(alerts)} alert(s)]" if alerts else ""
            return Check(
                "Performance monitor",
                passed=health != "critical",
                detail=f"Health: {health}{alert_str} | {total} tasks{score_str}",
                duration_ms=ms,
            )
        return Check("Performance monitor", passed=False,
                     detail=f"HTTP {status}", duration_ms=ms)
    except Exception as e:
        return Check("Performance monitor", passed=False, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

CHECKS = [
    check_health,
    check_stats,
    check_model_router,
    check_execute_endpoint,
    check_memory,
    check_schedules,
    check_projects,
    check_monitor_metrics,
]

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"


def run(base_url: str, api_key: str = "") -> bool:
    base = base_url.rstrip("/")
    print(f"\n  Pantheon COO OS — Health Check")
    print(f"  Target : {base}")
    print(f"  Auth   : {'apikey' if api_key else 'none'}")
    print(f"  {'─' * 52}")

    results: list[Check] = []
    for fn in CHECKS:
        check = fn(base, api_key)
        results.append(check)
        icon = PASS if check.passed else FAIL
        ms = f"{check.duration_ms:5.0f}ms" if check.duration_ms else "      "
        print(f"  {icon}  {check.name:<32} {ms}  {check.detail}")

    passed = sum(1 for c in results if c.passed)
    total = len(results)
    ok = passed == total

    print(f"  {'─' * 52}")
    overall = PASS if ok else FAIL
    print(f"  {overall}  {passed}/{total} checks passed\n")

    if not ok:
        failed = [c for c in results if not c.passed]
        print(f"  Failed checks:")
        for c in failed:
            print(f"    - {c.name}: {c.detail}")
        print()

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a running Pantheon COO OS deployment"
    )
    parser.add_argument("--url", default="http://localhost:8002",
                        help="Backend base URL (default: http://localhost:8002)")
    parser.add_argument("--key", default="",
                        help="API key (for AUTH_MODE=apikey deployments)")
    args = parser.parse_args()

    ok = run(args.url, args.key)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
