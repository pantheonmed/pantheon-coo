"""
tests/test_migrations.py
─────────────────────────
Tests for the database migration runner.
"""
import asyncio
import os
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "migrations"))


class TestMigrationRunner:
    @pytest.fixture
    def tmp_db(self, tmp_path):
        return str(tmp_path / "test_migrations.db")

    @pytest.fixture
    def tmp_versions(self, tmp_path):
        versions = tmp_path / "versions"
        versions.mkdir()
        return versions

    @pytest.mark.asyncio
    async def test_get_applied_on_fresh_db(self, tmp_db):
        from migrate import get_applied
        applied = await get_applied(tmp_db)
        assert isinstance(applied, set)
        assert len(applied) == 0

    @pytest.mark.asyncio
    async def test_schema_migrations_table_created(self, tmp_db):
        import aiosqlite
        from migrate import get_applied
        await get_applied(tmp_db)
        async with aiosqlite.connect(tmp_db) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ) as cur:
                row = await cur.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_apply_migration(self, tmp_db):
        from migrate import apply, get_applied
        sql = "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, val TEXT);"
        await apply(tmp_db, "0001", "test_migration", sql)
        applied = await get_applied(tmp_db)
        assert "0001" in applied

    @pytest.mark.asyncio
    async def test_migration_idempotent(self, tmp_db):
        from migrate import apply, get_applied
        sql = "CREATE TABLE IF NOT EXISTS idempotent_test (id INTEGER PRIMARY KEY);"
        await apply(tmp_db, "0001", "first", sql)
        await apply(tmp_db, "0001", "first", sql)  # second call should not fail
        applied = await get_applied(tmp_db)
        assert len(applied) == 1  # still only one

    @pytest.mark.asyncio
    async def test_run_migrations_applies_files(self, tmp_db, tmp_versions, monkeypatch):
        from migrate import run_migrations
        import migrate as migrate_mod
        monkeypatch.setattr(migrate_mod, "VERSIONS_DIR", tmp_versions)

        (tmp_versions / "0001_first.sql").write_text(
            "CREATE TABLE IF NOT EXISTS m1 (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        (tmp_versions / "0002_second.sql").write_text(
            "CREATE TABLE IF NOT EXISTS m2 (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )

        count = await run_migrations(tmp_db)
        assert count == 2

    @pytest.mark.asyncio
    async def test_run_migrations_skips_applied(self, tmp_db, tmp_versions, monkeypatch):
        from migrate import run_migrations, apply
        import migrate as migrate_mod
        monkeypatch.setattr(migrate_mod, "VERSIONS_DIR", tmp_versions)

        (tmp_versions / "0001_already.sql").write_text(
            "CREATE TABLE IF NOT EXISTS already (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        # Mark as applied before running
        await apply(tmp_db, "0001", "already", "SELECT 1;")

        count = await run_migrations(tmp_db)
        assert count == 0  # nothing new to apply

    @pytest.mark.asyncio
    async def test_initial_schema_migration_valid_sql(self, tmp_db):
        """The real 0001 migration file applies without error."""
        from migrate import apply
        sql_path = Path(__file__).parent.parent / "migrations" / "versions" / "0001_initial_schema.sql"
        if not sql_path.exists():
            pytest.skip("Migration file not found")
        sql = sql_path.read_text(encoding="utf-8")
        await apply(tmp_db, "0001", "initial_schema", sql)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ) as cur:
                tables = {row[0] for row in await cur.fetchall()}

        expected = {"tasks", "logs", "learnings", "schedules", "projects",
                    "agent_prompts", "briefings", "custom_tools", "task_patterns"}
        assert expected.issubset(tables)
