"""
tools/database.py — SQLite / PostgreSQL / MySQL read-write (sandboxed).
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from config import settings


def _ws_root() -> Path:
    return Path(settings.workspace_dir).resolve()


def _sqlite_path_from_url(p) -> Path:
    path_part = unquote(p.path or "")
    if not path_part:
        raise ValueError("SQLite URL must include a database path.")
    db_path = Path(path_part)
    if not db_path.is_absolute():
        db_path = (_ws_root() / db_path).resolve()
    else:
        db_path = db_path.resolve()
    return db_path


def _connect_any(cs: str):
    raw = (cs or "").strip()
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    if scheme == "sqlite":
        db_path = _sqlite_path_from_url(p)
        return sqlite3.connect(str(db_path)), "sqlite", db_path
    if scheme in ("postgresql", "postgres"):
        try:
            import psycopg2
        except ImportError as e:
            raise ValueError("PostgreSQL requires psycopg2-binary. pip install psycopg2-binary") from e
        conn = psycopg2.connect(raw)
        return conn, "postgresql", None
    if scheme == "mysql":
        try:
            import pymysql
        except ImportError as e:
            raise ValueError("MySQL requires pymysql. pip install pymysql") from e
        conn = pymysql.connect(
            host=p.hostname or "localhost",
            port=p.port or 3306,
            user=unquote(p.username or ""),
            password=unquote(p.password or ""),
            database=(p.path or "").lstrip("/").split("?")[0],
        )
        return conn, "mysql", None
    raise ValueError(f"Unsupported connection scheme: {scheme}")


def _connect_and_query(p: dict[str, Any]) -> dict[str, Any]:
    cs = str(p.get("connection_string", "")).strip()
    query = str(p.get("query", "")).strip()
    params = p.get("params") or []
    if not isinstance(params, (list, tuple)):
        params = []
    conn, kind, _ = _connect_any(cs)
    try:
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        if query.lstrip().upper().startswith("SELECT") or "RETURNING" in query.upper():
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
            if kind == "sqlite":
                rows = [list(r) for r in rows]
            else:
                rows = [list(r) for r in rows]
            return {"columns": columns, "rows": rows, "row_count": len(rows)}
        conn.commit()
        return {"columns": [], "rows": [], "row_count": cur.rowcount if cur.rowcount is not None else 0}
    finally:
        conn.close()


def _execute_statement(p: dict[str, Any]) -> dict[str, Any]:
    cs = str(p.get("connection_string", "")).strip()
    statement = str(p.get("statement", "")).strip()
    conn, _, _ = _connect_any(cs)
    try:
        cur = conn.cursor()
        cur.execute(statement)
        conn.commit()
        n = cur.rowcount
        return {"affected_rows": n if n is not None else 0, "success": True}
    finally:
        conn.close()


def _get_schema(p: dict[str, Any]) -> dict[str, Any]:
    cs = str(p.get("connection_string", "")).strip()
    conn, kind, _ = _connect_any(cs)
    tables: list[dict[str, Any]] = []
    try:
        cur = conn.cursor()
        if kind == "sqlite":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            names = [r[0] for r in cur.fetchall()]
            for name in names:
                cur.execute(f'PRAGMA table_info("{name}")')
                cols = [{"name": r[1], "type": r[2] or ""} for r in cur.fetchall()]
                tables.append({"name": name, "columns": cols})
        elif kind == "postgresql":
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            by_table: dict[str, list[dict[str, str]]] = {}
            for row in cur.fetchall():
                t, c, ty = row[0], row[1], row[2]
                by_table.setdefault(t, []).append({"name": c, "type": ty or ""})
            tables = [{"name": k, "columns": v} for k, v in sorted(by_table.items())]
        else:  # mysql
            cur.execute("SHOW TABLES")
            names = [r[0] for r in cur.fetchall()]
            for name in names:
                cur.execute(f"DESCRIBE `{name}`")
                cols = []
                for r in cur.fetchall():
                    t = r[1]
                    if isinstance(t, bytes):
                        t = t.decode()
                    cols.append({"name": r[0], "type": str(t)})
                tables.append({"name": name, "columns": cols})
        return {"tables": tables}
    finally:
        conn.close()


def _backup_sqlite(p: dict[str, Any]) -> dict[str, Any]:
    db_path = Path(str(p.get("db_path", ""))).resolve()
    backup_path = Path(str(p.get("backup_path", ""))).resolve()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    shutil.copy2(db_path, backup_path)
    return {"backup_path": str(backup_path), "size_bytes": backup_path.stat().st_size}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    if act == "connect_and_query":
        return _connect_and_query(params)
    if act == "execute_statement":
        return _execute_statement(params)
    if act == "get_schema":
        return _get_schema(params)
    if act == "backup_sqlite":
        return _backup_sqlite(params)
    raise ValueError(
        f"Unknown database action: '{action}'. "
        "Available: connect_and_query, execute_statement, get_schema, backup_sqlite"
    )
