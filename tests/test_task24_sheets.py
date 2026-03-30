"""
Task 24 — Google Sheets tool: registry, sandbox validation, mocked httpx.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_spreadsheet_id, validate_step
from tools import REGISTRY


# Valid length (20–80) and charset for sandbox + tool
VALID_SPREADSHEET_ID = "a" * 40


def test_toolname_google_sheets_enum():
    assert ToolName.GOOGLE_SHEETS.value == "google_sheets"


def test_google_sheets_in_registry():
    import tools.google_sheets as gs_mod

    assert ToolName.GOOGLE_SHEETS in REGISTRY
    assert REGISTRY[ToolName.GOOGLE_SHEETS] is gs_mod


def test_validate_spreadsheet_id_rejects_spaces():
    with pytest.raises(SecurityError, match="whitespace"):
        validate_spreadsheet_id(VALID_SPREADSHEET_ID + " ")


def test_validate_spreadsheet_id_rejects_short():
    with pytest.raises(SecurityError, match="20"):
        validate_spreadsheet_id("short")


def test_validate_spreadsheet_id_rejects_traversal():
    with pytest.raises(SecurityError, match="forbidden"):
        validate_spreadsheet_id(VALID_SPREADSHEET_ID[:35] + "../evil")


def test_sandbox_google_sheets_step():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.GOOGLE_SHEETS,
        action="read_sheet",
        params={"spreadsheet_id": VALID_SPREADSHEET_ID, "range": "A1:B2"},
        status=StepStatus.PENDING,
    )
    validate_step(step)


def test_sandbox_create_sheet_skips_spreadsheet_id():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.GOOGLE_SHEETS,
        action="create_sheet",
        params={"title": "My Sheet"},
        status=StepStatus.PENDING,
    )
    validate_step(step)


@pytest.mark.asyncio
async def test_read_sheet_returns_mocked_data(monkeypatch):
    monkeypatch.setattr("tools.google_sheets._access_token_sync", lambda: "fake-token")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {"values": [["a", "b"], ["1", "2"]]}
    mock_resp.text = ""

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.google_sheets.httpx.AsyncClient", return_value=mock_cm):
        from tools.google_sheets import execute

        out = await execute(
            "read_sheet",
            {"spreadsheet_id": VALID_SPREADSHEET_ID, "range": "Sheet1!A1:B2"},
        )

    assert out["ok"] is True
    assert out["body"]["values"] == [["a", "b"], ["1", "2"]]
    mock_client.request.assert_called_once()
    assert mock_client.request.call_args[0][0] == "GET"


@pytest.mark.asyncio
async def test_write_sheet_sends_correct_payload(monkeypatch):
    monkeypatch.setattr("tools.google_sheets._access_token_sync", lambda: "fake-token")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.is_success = True
    mock_resp.json.return_value = {"updatedCells": 2}
    mock_resp.text = ""

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.google_sheets.httpx.AsyncClient", return_value=mock_cm):
        from tools.google_sheets import execute

        await execute(
            "write_sheet",
            {
                "spreadsheet_id": VALID_SPREADSHEET_ID,
                "range": "Sheet1!A1",
                "values": [["x", "y"]],
            },
        )

    call = mock_client.request.call_args
    assert call[0][0] == "PUT"
    content = call[1].get("content") or ""
    assert "x" in content and "y" in content
    assert "values" in content
