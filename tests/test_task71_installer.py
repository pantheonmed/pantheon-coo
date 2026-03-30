"""Task 71 — install.sh / uninstall.sh universal installer."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_install_sh_exists():
    p = ROOT / "install.sh"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in text or "#!/bin/bash" in text
    assert "python3" in text
    assert "git" in text


def test_install_sh_checks_python():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "command -v python3" in text or "command -v python3 &>" in text


def test_install_sh_checks_git():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "command -v git" in text


def test_uninstall_sh_exists():
    assert (ROOT / "uninstall.sh").is_file()


@pytest.mark.parametrize("script", ["install.sh", "uninstall.sh"])
def test_scripts_pass_bash_n(script: str):
    p = ROOT / script
    r = subprocess.run(
        ["bash", "-n", str(p)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
