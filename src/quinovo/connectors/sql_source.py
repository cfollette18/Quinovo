"""SQL source: a read-only query becomes objects.

SQLite always works (stdlib). Postgres uses an optional driver; if none is
installed the source fails with a clear message instead of pulling in a
heavy dependency.
"""

from __future__ import annotations

from typing import Any

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.connectors.mapping import upsert_rows
from quinovo.engine.sql import open_sql_connection, rows_from_query
from quinovo.engine.store import ObjectStore


class SqlSource:
    """Run one SELECT (or equivalent) and upsert each row as an object.

    config:
        dsn / path: str     — sqlite file path, ``sqlite:///…``, or postgres URL.
        query: str          — read-only SQL.
        id_field: str       — optional field to copy onto the object id.
        property_map: dict  — optional rename map.
    """

    kind = "sql"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        query = record.config.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ConnectorError("sql source needs a query")
        dsn = _dsn(record.config)
        if not dsn:
            raise ConnectorError("sql source needs a database path or connection URL")
        try:
            conn = open_sql_connection(dsn)
        except Exception as exc:
            raise ConnectorError(str(exc)) from exc
        try:
            rows = rows_from_query(conn, query)
        except Exception as exc:
            raise ConnectorError("sql source query failed") from exc
        finally:
            conn.close()
        return upsert_rows(store, record, rows, f"{len(rows)} rows from the database")


def _dsn(config: dict[str, Any]) -> str:
    for key in ("dsn", "path", "url"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
