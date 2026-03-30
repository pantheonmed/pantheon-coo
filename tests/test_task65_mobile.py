"""Task 65 — React Native (Expo) mobile app scaffold."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MA = ROOT / "mobile_app"


def test_mobile_app_directory_exists():
    assert MA.is_dir()


def test_app_tsx_has_navigation():
    text = (MA / "App.tsx").read_text(encoding="utf-8")
    assert "NavigationContainer" in text
    assert "createBottomTabNavigator" in text or "Tab.Navigator" in text


def test_package_json_has_expo():
    text = (MA / "package.json").read_text(encoding="utf-8")
    assert '"expo"' in text
    assert "~51.0.0" in text or "51.0" in text


def test_api_ts_has_execute():
    text = (MA / "services" / "api.ts").read_text(encoding="utf-8")
    assert "execute" in text
    assert "export async function execute" in text


def test_readme_setup():
    text = (MA / "README.md").read_text(encoding="utf-8")
    assert "npm install" in text.lower() or "npm install" in text
    assert "expo start" in text.lower() or "npx expo" in text


@pytest.mark.parametrize(
    "name",
    [
        "LoginScreen.tsx",
        "DashboardScreen.tsx",
        "TaskDetailScreen.tsx",
        "VoiceScreen.tsx",
        "SettingsScreen.tsx",
    ],
)
def test_screen_files_exist(name):
    assert (MA / "screens" / name).is_file()
