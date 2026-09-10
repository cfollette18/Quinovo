"""Small SQL connection helper. SQLite is always available; Postgres is optional."""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

try:
    import psycopg
except ImportError:
    psycopg = None  # type: ignore[assignment]

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]


class SqlConnection(Protocol):
    def cursor(self) -> Any: ...
    def close(self) -> None: ...
    def commit(self) -> None: ...
    def execute(self, query: str, params: Any = ...) -> Any: ...


def is_postgres_dsn(dsn: str) -> bool:
    lowered = dsn.lower()
    return lowered.startswith("postgres://") or lowered.startswith("postgresql://")


def postgres_driver_available() -> bool:
    return psycopg is not None or psycopg2 is not None


def open_sql_connection(dsn: str) -> Any:
    """Open SQLite for a file path / sqlite URL, or Postgres when a driver exists."""
    if is_postgres_dsn(dsn):
        return _open_postgres(dsn)
    path = dsn
    if path.startswith("sqlite:///"):
        path = path[len("sqlite:///") :]
    elif path.startswith("sqlite://"):
        path = path[len("sqlite://") :]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _open_postgres(dsn: str) -> Any:
    if psycopg is not None:
        return psycopg.connect(dsn)
    if psycopg2 is not None:
        return psycopg2.connect(dsn)
    raise RuntimeError(
        "postgres is not available here — install a driver, or use a sqlite file"
    )


def rows_from_query(conn: Any, query: str, params: Any = None) -> list[dict[str, Any]]:
    """Run a read query and return dict rows. Caller closes the connection."""
    if hasattr(conn, "execute") and not hasattr(conn, "cursor"):
        cursor = conn.execute(query) if params is None else conn.execute(query, params)
        rows = cursor.fetchall()
        names = [col[0] for col in cursor.description] if cursor.description else []
        return [_as_dict(row, names) for row in rows]
    cursor = conn.cursor()
    try:
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        rows = cursor.fetchall()
        names = [col[0] for col in cursor.description] if cursor.description else []
        return [_as_dict(row, names) for row in rows]
    finally:
        cursor.close()


def execute_write(conn: Any, statement: str, params: Any = None) -> int:
    """Run one write statement. Returns rowcount when the driver provides it."""
    if hasattr(conn, "execute") and isinstance(conn, sqlite3.Connection):
        cursor = conn.execute(statement) if params is None else conn.execute(statement, params)
        conn.commit()
        return int(cursor.rowcount or 0)
    cursor = conn.cursor()
    try:
        if params is None:
            cursor.execute(statement)
        else:
            cursor.execute(statement, params)
        conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)
    finally:
        cursor.close()


def _as_dict(row: Any, names: list[str]) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    if names:
        return {names[index]: row[index] for index in range(min(len(names), len(row)))}
    return {}
