"""Connector registry: maps source records to connector implementations.

Sources are persisted in the store so they survive reload. Programmatic
callables can also be registered in-memory (used by tests and agents that want
a custom pull function).
"""

from __future__ import annotations

from collections.abc import Callable

from quinovo.connectors.base import (
    Connector,
    ConnectorError,
    SourceRecord,
    SourceRun,
    run_source,
)
from quinovo.connectors.csv_source import CsvSource
from quinovo.connectors.http_source import HttpSource
from quinovo.connectors.json_source import JsonSource
from quinovo.connectors.mcp_source import McpSource
from quinovo.connectors.sql_source import SqlSource
from quinovo.connectors.synthetic import SyntheticSource
from quinovo.connectors.transcripts import TranscriptsSource
from quinovo.connectors.webhook_source import WebhookSource
from quinovo.connectors.youtube import YoutubeSource
from quinovo.engine.store import ObjectStore

_BUILTIN: dict[str, Connector] = {
    "synthetic": SyntheticSource(),
    "csv": CsvSource(),
    "http": HttpSource(),
    "json": JsonSource(),
    "webhook": WebhookSource(),
    "sql": SqlSource(),
    "mcp": McpSource(),
    "transcripts": TranscriptsSource(),
    "youtube": YoutubeSource(),
}

CallableConnector = Callable[[ObjectStore, SourceRecord], SourceRun]


class _CallableConnector:
    kind = "callable"

    def __init__(self, fn: CallableConnector) -> None:
        self._fn = fn

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        return self._fn(store, record)


class ConnectorRegistry:
    """Holds built-in connectors plus any programmatic callable connectors."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = dict(_BUILTIN)
        self._callables: dict[str, _CallableConnector] = {}

    def register_callable(self, name: str, fn: CallableConnector) -> None:
        self._callables[name] = _CallableConnector(fn)

    def kinds(self) -> list[str]:
        return sorted(self._connectors.keys() | self._callables.keys() | {"callable"})

    def connector_for(self, record: SourceRecord) -> Connector:
        if record.name in self._callables:
            return self._callables[record.name]
        connector = self._connectors.get(record.kind)
        if connector is None:
            raise ConnectorError(
                f"unknown connector kind {record.kind!r}; known: {self.kinds()}"
            )
        return connector

    def pull(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        connector = self.connector_for(record)
        return run_source(store, record, connector)


def build_registry() -> ConnectorRegistry:
    return ConnectorRegistry()
