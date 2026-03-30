"""Task 92 — Smoke integration checks for launch batch routes."""
from __future__ import annotations


def test_marketplace_public_list(client):
    r = client.get("/marketplace")
    assert r.status_code == 200
    assert "tools" in r.json()


def test_ready_probe_public(client):
    assert client.get("/ready").status_code == 200


def test_health_has_worker_fields(client):
    h = client.get("/health").json()
    assert "worker_count" in h
    assert "ready" in h
