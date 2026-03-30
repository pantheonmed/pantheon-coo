"""
migrations/migrate.py
──────────────────────
Database migration runner for Pantheon COO OS.

SQLite doesn't have ALTER COLUMN or DROP COLUMN, but it does have:
  - ADD COLUMN (safe, non-destructive)
  - CREATE TABLE IF NOT EXISTS (idempotent)
  - CREATE INDEX IF NOT EXISTS (idempotent)

This runner applies numbered migration files in order, tracking applied
migrations in a `schema_migrations` table so each runs exactly once.

Usage:
  python3 migrations/migrate.py                 # apply pending migrations
  python3 migrations/migrate.py --status        # show migration state
  python3 migrations/migrate.py --rollback N    # future: rollback to version N

Migration files live in migrations/versions/
Named: NNNN_description.sql  (e.g. 0001_initial_schema.sql)

Each file contains idempotent SQL (IF NOT EXISTS everywhere).
"""
from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


VERSIONS_DIR = Path(__file__).parent / "versions"
SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


async def _get_db_path() -> str:
    from config import settings
    return settings.db_path


async def get_applied(db_path: str) -> set[str]:
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(SCHEMA_MIGRATIONS_DDL)
        await db.commit()
        async with db.execute("SELECT version FROM schema_migrations ORDER BY version") as cur:
            return {row[0] for row in await cur.fetchall()}


async def apply(db_path: str, version: str, name: str, sql: str) -> None:
    import aiosqlite
    # Ensure schema_migrations table exists before inserting
    async with aiosqlite.connect(db_path) as db:
        await db.execute(SCHEMA_MIGRATIONS_DDL)
        await db.commit()
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(sql)
        await db.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?,?,?)",
            (version, name, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
    print(f"  ✓ {version} — {name}")


async def run_migrations(db_path: str) -> int:
    """Apply all pending migrations. Returns count applied."""
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    applied = await get_applied(db_path)

    migration_files = sorted(VERSIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("  No migration files found in migrations/versions/")
        return 0

    count = 0
    for mf in migration_files:
        version = mf.stem.split("_")[0]  # "0001" from "0001_initial_schema"
        name = "_".join(mf.stem.split("_")[1:])  # "initial_schema"

        if version in applied:
            continue

        sql = mf.read_text(encoding="utf-8")
        await apply(db_path, version, name, sql)
        count += 1

    return count


async def show_status(db_path: str) -> None:
    """Print migration status table."""
    import aiosqlite
    applied = await get_applied(db_path)

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    migration_files = sorted(VERSIONS_DIR.glob("*.sql"))

    print(f"\n{'Version':<8} {'Status':<10} {'Name'}")
    print("─" * 50)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ) as cur:
            applied_rows = {r["version"]: r for r in await cur.fetchall()}

    all_versions: set[str] = set()
    for mf in migration_files:
        version = mf.stem.split("_")[0]
        name = "_".join(mf.stem.split("_")[1:])
        all_versions.add(version)
        status = "applied" if version in applied else "PENDING"
        ts = applied_rows[version]["applied_at"][:19] if version in applied_rows else ""
        print(f"{version:<8} {status:<10} {name}  {ts}")

    if not all_versions:
        print("  (no migration files)")
    print()


async def main() -> None:
    db_path = await _get_db_path()
    args = sys.argv[1:]

    if "--status" in args:
        await show_status(db_path)
        return

    print(f"\nPantheon COO OS — DB Migrations")
    print(f"DB: {db_path}")
    print(f"{'─' * 40}")

    applied = await get_applied(db_path)
    total_files = len(list(VERSIONS_DIR.glob("*.sql"))) if VERSIONS_DIR.exists() else 0
    pending = total_files - len(applied)

    if pending == 0:
        print(f"  Already up to date. ({len(applied)} migration(s) applied)")
    else:
        print(f"  Applying {pending} pending migration(s)...")
        count = await run_migrations(db_path)
        print(f"\n  Done. {count} migration(s) applied.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
