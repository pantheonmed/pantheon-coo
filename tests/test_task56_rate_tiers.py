"""Task 56 — Plan-based API rate limits."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from security.rate_limit import PLAN_RATE_LIMITS, plan_limits_for_auth


def test_plan_rate_limits_all_four_plans():
    assert set(PLAN_RATE_LIMITS.keys()) == {"free", "starter", "pro", "pro_monthly", "enterprise"}
    assert PLAN_RATE_LIMITS["free"]["execute_rpm"] == 3
    assert PLAN_RATE_LIMITS["starter"]["execute_rpm"] == 10
    assert PLAN_RATE_LIMITS["pro"]["execute_rpm"] == 30
    assert PLAN_RATE_LIMITS["enterprise"]["execute_rpm"] == 100


def test_plan_from_auth_dict():
    assert plan_limits_for_auth({"plan": "pro"})["global_rpm"] == 60
    assert plan_limits_for_auth({"plan": "unknown"}) == PLAN_RATE_LIMITS["free"]


def test_get_usage_includes_rate_limits(client: TestClient):
    r = client.get("/usage")
    assert r.status_code == 200
    j = r.json()
    assert "rate_limits" in j
    rl = j["rate_limits"]
    for k in ("global_rpm", "execute_rpm", "current_global_usage", "current_execute_usage"):
        assert k in rl


def test_starter_plan_execute_limit():
    assert plan_limits_for_auth({"plan": "starter"})["execute_rpm"] == 10


def test_enterprise_plan_global_limit():
    assert plan_limits_for_auth({"plan": "enterprise"})["global_rpm"] == 60


def test_free_plan_global_limit():
    assert plan_limits_for_auth({"plan": "free"})["global_rpm"] == 60


def test_usage_default_plan_free_when_missing():
    assert plan_limits_for_auth({})["execute_rpm"] == 3
