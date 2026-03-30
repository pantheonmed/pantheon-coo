"""Task 70 — Chrome extension scaffold."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CE = ROOT / "chrome_extension"


def test_chrome_extension_dir():
    assert CE.is_dir()


def test_manifest_valid_json():
    data = json.loads((CE / "manifest.json").read_text(encoding="utf-8"))
    assert data["manifest_version"] == 3
    assert data["name"] == "Pantheon COO"


def test_popup_html_exists():
    assert (CE / "popup.html").is_file()


def test_popup_js_has_execute():
    text = (CE / "popup.js").read_text(encoding="utf-8")
    assert "function execute" in text or "async function execute" in text


def test_readme_install():
    text = (CE / "README.md").read_text(encoding="utf-8")
    assert "Load unpacked" in text or "developer" in text.lower()
