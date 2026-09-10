"""Connector protocol and the run result shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from quinovo.engine.store import ObjectStore, SourceRecord


class ConnectorError(Exception):
    """A connector could not run or produced invalid objects."""


@dataclass
class SourceRun:
    upserted: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""


class Connector(Protocol):
    """A connector pulls external rows and upserts them as ontology objects."""

    kind: str

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        ...


def run_source(store: ObjectStore, record: SourceRecord, connector: Connector) -> SourceRun:
    """Run one connector against the store. Returns upserted object payloads."""
    return connector.run(store, record)
