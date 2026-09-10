"""JSON feed: poll a URL that returns an array (or a common wrapper) of objects."""

from __future__ import annotations

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.connectors.mapping import extract_rows, fetch_json, upsert_rows
from quinovo.engine.store import ObjectStore


class JsonSource:
    """GET a JSON array and upsert each element as one object.

    config:
        url: str            — feed URL.
        rows_path: str      — optional dotted path to the array.
        id_field: str       — optional field to copy onto the object id.
        property_map: dict  — optional rename map.
        headers: dict       — optional request headers. Never log these.
    """

    kind = "json"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        url = record.config.get("url")
        if not isinstance(url, str) or not url:
            raise ConnectorError("json source needs a URL")
        headers = record.config.get("headers") or {}
        if not isinstance(headers, dict):
            raise ConnectorError("json source headers must be a mapping")
        payload = fetch_json(url, headers)
        rows_path = record.config.get("rows_path")
        path = rows_path if isinstance(rows_path, str) and rows_path else None
        rows = extract_rows(payload, path, singleton=True)
        return upsert_rows(store, record, rows, f"{len(rows)} rows from the feed")
