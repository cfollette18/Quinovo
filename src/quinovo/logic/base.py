"""Logic source protocol and result shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from quinovo.engine.store import LogicSourceRecord as SourceRecord
from quinovo.engine.store import ObjectStore


class LogicError(Exception):
    """A logic source failed or returned invalid facts/forecasts."""


@dataclass
class LogicResult:
    facts: list[dict[str, Any]] = field(default_factory=list)
    forecasts: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""


class LogicSource(Protocol):
    """A logic source produces inferred facts/forecasts and writes them in."""

    kind: str

    def run(self, store: ObjectStore, record: SourceRecord) -> LogicResult:
        ...


def run_logic(store: ObjectStore, record: SourceRecord, source: LogicSource) -> LogicResult:
    return source.run(store, record)
