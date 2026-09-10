"""Synthetic source: upsert objects from a row template. Honest demo/test connector."""

from __future__ import annotations

from typing import Any

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.engine.store import ObjectStore


class SyntheticSource:
    """Upsert a list of property dicts into one object type.

    config:
        rows: list[dict]  — each dict is the full property set for one object.
    """

    kind = "synthetic"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        rows = record.config.get("rows")
        if not isinstance(rows, list):
            raise ConnectorError("synthetic source needs config.rows (a list of property dicts)")
        upserted: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ConnectorError("synthetic source rows must be property dicts")
            obj = store.upsert_object(record.object_type, row, source="funnel")
            upserted.append(
                {"type": obj.object_type, "id": obj.id, "version": obj.version}
            )
        return SourceRun(upserted=upserted, detail=f"{len(upserted)} objects")
