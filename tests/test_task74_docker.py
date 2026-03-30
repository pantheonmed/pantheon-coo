"""Task 74 — Docker Hub / compose production layout."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_has_healthcheck():
    yml = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "healthcheck:" in yml
    assert "pantheonai/coo-os:latest" in yml or "pantheonai/coo-os" in yml


def test_docker_compose_valid_structure():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "version:" in text
    assert "services:" in text
    assert "backend:" in text
    assert "volumes:" in text


def test_docker_start_exists():
    assert (ROOT / "docker-start.sh").is_file()


def test_docker_start_bash_n():
    r = subprocess.run(
        ["bash", "-n", str(ROOT / "docker-start.sh")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_docker_md_exists():
    assert (ROOT / "DOCKER.md").is_file()


def test_dockerfile_has_healthcheck_instruction():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in df
