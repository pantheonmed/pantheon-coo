"""Task 77 — GitHub templates, CI workflow, contributor docs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_exists():
    p = ROOT / ".github" / "workflows" / "ci.yml"
    assert p.is_file()


def test_ci_yml_valid_yaml_and_pytest():
    raw = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert raw.strip().startswith("name:")
    assert "pytest" in raw
    try:
        import yaml  # type: ignore
    except ImportError:
        return
    data = yaml.safe_load(raw)
    assert data.get("name") == "CI"
    assert "jobs" in data


def test_contributing_exists():
    assert (ROOT / "CONTRIBUTING.md").is_file()


def test_security_md_exists():
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "security@pantheon.ai" in text
    assert "GitHub" in text or "github" in text.lower()


def test_bug_report_template_exists():
    p = ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md"
    assert p.is_file()
    t = p.read_text(encoding="utf-8")
    assert "Bug Description" in t
