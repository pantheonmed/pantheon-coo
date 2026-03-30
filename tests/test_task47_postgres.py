"""Task 47 — DBPool PostgreSQL detection + docker/migration artifacts."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings
from memory.db_pool import DBPool, normalize_asyncpg_dsn


def test_dbpool_defaults_sqlite_backend():
    with patch.object(settings, "database_url", ""):
        p = DBPool(":memory:")
        assert p.backend == "sqlite"


def test_dbpool_detects_postgresql_from_database_url():
    with patch.object(
        settings,
        "database_url",
        "postgresql+asyncpg://u:p@localhost:5432/db",
    ):
        p = DBPool("x.db")
        assert p.backend == "postgresql"
        assert p._pg_dsn is not None
        assert "postgresql://" in p._pg_dsn
        assert "+asyncpg" not in p._pg_dsn


def test_normalize_asyncpg_dsn():
    assert "postgresql://" in normalize_asyncpg_dsn("postgresql+asyncpg://h/db")


def test_asyncpg_in_requirements():
    req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "asyncpg==0.29.0" in req


def test_docker_compose_has_postgres_service():
    dc = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert "postgres:" in dc
    assert "postgres:16-alpine" in dc
    assert "profiles:" in dc
    assert "pantheon_coo_postgres" in dc


def test_migration_0012_exists():
    m = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0012_postgres_compat.sql"
    assert m.is_file()
    text = m.read_text(encoding="utf-8")
    assert "PostgreSQL" in text or "postgres" in text.lower()
