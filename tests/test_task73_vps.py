"""Task 73 — VPS setup script + doc."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vps_setup_exists():
    assert (ROOT / "vps_setup.sh").is_file()


def test_vps_setup_passes_bash_n():
    r = subprocess.run(
        ["bash", "-n", str(ROOT / "vps_setup.sh")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_vps_setup_contains_nginx_and_systemd():
    t = (ROOT / "vps_setup.sh").read_text(encoding="utf-8")
    assert "nginx" in t.lower()
    assert "pantheon-coo.service" in t or "systemd" in t.lower()


def test_vps_deploy_md_exists():
    assert (ROOT / "VPS_DEPLOY.md").is_file()
