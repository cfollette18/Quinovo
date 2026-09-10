"""Inbound webhook: other systems push objects to ``POST /ingest/{name}``.

Pull is a no-op. The source exists so the mapping, token, and last-push
status live next to every other connection.
"""

from __future__ import annotations

from quinovo.connectors.base import SourceRecord, SourceRun
from quinovo.engine.store import ObjectStore


class WebhookSource:
    """A named inbox. Other systems POST rows; Quinovo maps them to objects.

    config:
        token: str          — optional shared secret. Never log it.
        rows_path: str      — optional dotted path to the rows list.
        id_field: str       — optional field to copy onto the object id.
        property_map: dict  — optional rename map.
    """

    kind = "webhook"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        del store
        name = record.name
        return SourceRun(
            upserted=[],
            detail=f"Waiting for another system to POST /ingest/{name}",
        )
