"""CSV source: read a CSV file and upsert each row as an ontology object."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.connectors.mapping import upsert_rows
from quinovo.engine.store import ObjectStore


class CsvSource:
    """Read a CSV file; each row becomes one object of ``object_type``.

    config:
        path: str           — path to the CSV file (relative to cwd or absolute).
        delimiter: str      — optional, default ",".
        id_field: str       — optional column to copy onto the object id.
        property_map: dict  — optional column_name -> property_name rename map.
    """

    kind = "csv"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        raw_path = record.config.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise ConnectorError("csv source needs a file path")
        path = Path(raw_path)
        delimiter = record.config.get("delimiter") or ","
        if not path.exists():
            raise ConnectorError(f"csv source file not found: {path}")
        rows: list[dict[str, Any]] = []
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                rows.append({key: value for key, value in row.items() if key is not None})
        return upsert_rows(store, record, rows, f"{len(rows)} rows from {path.name}")
