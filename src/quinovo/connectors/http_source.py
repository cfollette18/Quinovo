"""HTTP source: fetch JSON rows from an endpoint and upsert them as objects.

This is the MCP-as-connector pattern made concrete: any HTTP endpoint that
returns a list of objects (or {"rows": [...]}) becomes a Quinovo source.
"""

from __future__ import annotations

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.connectors.mapping import extract_rows, fetch_json, upsert_rows
from quinovo.engine.store import ObjectStore


class HttpSource:
    """Fetch JSON from a URL; upsert each row as one object.

    config:
        url: str            — endpoint URL.
        rows_path: str      — optional dotted path to the rows list (default: top-level list
                              or the "rows"/"data"/"items" key).
        id_field: str       — optional field to copy onto the object id.
        property_map: dict  — optional rename map.
        headers: dict       — optional request headers. Never log these.
    """

    kind = "http"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        url = record.config.get("url")
        if not isinstance(url, str) or not url:
            raise ConnectorError("http source needs a URL")
        headers = record.config.get("headers") or {}
        if not isinstance(headers, dict):
            raise ConnectorError("http source headers must be a mapping")
        payload = fetch_json(url, headers)
        rows_path = record.config.get("rows_path")
        path = rows_path if isinstance(rows_path, str) and rows_path else None
        rows = extract_rows(payload, path)
        return upsert_rows(store, record, rows, f"{len(rows)} rows from {url}")
