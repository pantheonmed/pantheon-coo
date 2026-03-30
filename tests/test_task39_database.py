"""Task 39 — database connector tool + sandbox."""
from __future__ import annotations

import sqlite3

import pytest

from config import settings
from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import REGISTRY
from tools import database as db_mod


@pytest.mark.asyncio
async def test_connect_and_query_select(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    dbf = tmp_path / "test.db"
    conn = sqlite3.connect(str(dbf))
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    conn.close()
    cs = f"sqlite:///{dbf}"
    r = await db_mod.execute(
        "connect_and_query",
        {"connection_string": cs, "query": "SELECT id, name FROM t ORDER BY id", "params": []},
    )
    assert r["columns"] == ["id", "name"]
    assert r["rows"] == [[1, "a"], [2, "b"]]
    assert r["row_count"] == 2


@pytest.mark.asyncio
async def test_drop_table_blocked_by_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    dbf = tmp_path / "test.db"
    sqlite3.connect(str(dbf)).close()
    cs = f"sqlite:///{dbf}"
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.DATABASE,
        action="connect_and_query",
        params={"connection_string": cs, "query": "DROP TABLE t"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError, match="DROP"):
        validate_step(step)


@pytest.mark.asyncio
async def test_delete_without_where_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    dbf = tmp_path / "test.db"
    cs = f"sqlite:///{dbf}"
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.DATABASE,
        action="connect_and_query",
        params={"connection_string": cs, "query": "DELETE FROM users"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError, match="DELETE"):
        validate_step(step)


@pytest.mark.asyncio
async def test_get_schema_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    dbf = tmp_path / "test.db"
    conn = sqlite3.connect(str(dbf))
    conn.execute("CREATE TABLE alpha (x INT)")
    conn.commit()
    conn.close()
    cs = f"sqlite:///{dbf}"
    r = await db_mod.execute("get_schema", {"connection_string": cs})
    names = {t["name"] for t in r["tables"]}
    assert "alpha" in names


@pytest.mark.asyncio
async def test_backup_sqlite_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    dbf = tmp_path / "src.db"
    c = sqlite3.connect(str(dbf))
    c.execute("CREATE TABLE q (n INT)")
    c.commit()
    c.close()
    backup = tmp_path / "back" / "copy.db"
    r = await db_mod.execute(
        "backup_sqlite",
        {"db_path": str(dbf), "backup_path": str(backup)},
    )
    assert backup.is_file()
    assert r["size_bytes"] > 0


def test_toolname_database_enum():
    from models import ToolName

    assert ToolName.DATABASE.value == "database"


def test_database_in_registry():
    assert ToolName.DATABASE in REGISTRY
    assert REGISTRY[ToolName.DATABASE] is db_mod
