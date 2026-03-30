#!/usr/bin/env python3
"""
Load test script for Pantheon COO OS.
Usage: python3 scripts/load_test.py --url http://localhost:8002 --users 5
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx


async def test_user(client: httpx.AsyncClient, base_url: str, user_num: int):
    results = []
    email = f"loadtest_{user_num}_{int(time.time())}@test.com"
    r = await client.post(
        f"{base_url}/auth/register",
        json={
            "email": email,
            "name": f"Test {user_num}",
            "password": "Test1234!",
        },
    )
    if r.status_code != 200:
        return [{"status": "register_failed", "code": r.status_code}]

    api_key = r.json().get("api_key", "")
    headers = {"X-COO-API-Key": api_key}

    for i in range(3):
        t0 = time.monotonic()
        r = await client.post(
            f"{base_url}/execute",
            json={"command": f"echo load test {user_num} task {i}"},
            headers=headers,
        )
        elapsed = (time.monotonic() - t0) * 1000
        results.append(
            {
                "status": "ok" if r.status_code == 202 else "error",
                "code": r.status_code,
                "ms": round(elapsed),
            }
        )

    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8002")
    parser.add_argument("--users", type=int, default=5)
    args = parser.parse_args()

    print(f"\nLoad test: {args.users} concurrent users → {args.url}")
    print("─" * 50)

    async with httpx.AsyncClient(timeout=30) as client:
        t0 = time.monotonic()
        tasks = [test_user(client, args.url, i) for i in range(args.users)]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        total_ms = (time.monotonic() - t0) * 1000

    all_flat: list = []
    for results in all_results:
        if isinstance(results, list):
            all_flat.extend(results)

    ok = sum(1 for r in all_flat if r.get("status") == "ok")
    errors = len(all_flat) - ok
    avg_ms = sum(r.get("ms", 0) for r in all_flat) / max(len(all_flat), 1)

    print(f"  Total requests : {len(all_flat)}")
    print(f"  Successful     : {ok}")
    print(f"  Errors         : {errors}")
    print(f"  Avg response   : {avg_ms:.0f}ms")
    print(f"  Total time     : {total_ms:.0f}ms")
    print(f"  Success rate   : {ok/max(len(all_flat),1)*100:.1f}%")
    print()

    if errors > 0:
        print("  LOAD TEST FAILED — errors detected")
        sys.exit(1)
    print("  LOAD TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
