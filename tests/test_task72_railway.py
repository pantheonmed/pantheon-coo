"""Task 72 — Railway config + Dockerfile."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_railway_json_valid():
    p = ROOT / "railway.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "build" in data
    assert "deploy" in data
    assert data["build"].get("builder") == "DOCKERFILE"
    assert data["deploy"].get("healthcheckPath") == "/health"


def test_railway_deploy_doc_exists():
    assert (ROOT / "RAILWAY_DEPLOY.md").is_file()


def test_dockerfile_python_slim_base():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.11-slim" in text
    assert "uvicorn main_railway:app" in text


def test_dockerfile_has_healthcheck():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in text
    assert "/health" in text


def test_dockerfile_syntax_check():
    """Basic structural check without requiring Docker daemon."""
    df = ROOT / "Dockerfile"
    lines = df.read_text(encoding="utf-8").splitlines()
    assert any(l.strip().upper().startswith("FROM ") for l in lines)
    assert any("CMD" in l.upper() for l in lines)
