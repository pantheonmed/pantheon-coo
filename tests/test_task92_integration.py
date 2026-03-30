"""Task 92 — Smoke integration checks for launch batch routes."""
from __future__ import annotations


def test_marketplace_public_list(client):
    r = client.get("/marketplace")
    assert r.status_code == 200
    assert "tools" in r.json()


def test_ready_probe_public(client):
    assert client.get("/ready").status_code == 200


def test_ready_has_queue_fields(client):
    r = client.get("/ready").json()
    assert r.get("ok") is True
    assert "queue_depth" in r
