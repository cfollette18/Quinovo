"""Logic registry: maps logic source records to implementations."""

from __future__ import annotations

from collections.abc import Callable

from quinovo.engine.store import ObjectStore
from quinovo.logic.base import (
    LogicError,
    LogicResult,
    LogicSource,
    SourceRecord,
    run_logic,
)
from quinovo.logic.http_source import HttpLogicSource

_BUILTIN: dict[str, LogicSource] = {
    "http": HttpLogicSource(),
}

CallableLogic = Callable[[ObjectStore, SourceRecord], LogicResult]


class _CallableLogic:
    kind = "callable"

    def __init__(self, fn: CallableLogic) -> None:
        self._fn = fn

    def run(self, store: ObjectStore, record: SourceRecord) -> LogicResult:
        return self._fn(store, record)


class LogicRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, LogicSource] = dict(_BUILTIN)
        self._callables: dict[str, _CallableLogic] = {}

    def register_callable(self, name: str, fn: CallableLogic) -> None:
        self._callables[name] = _CallableLogic(fn)

    def kinds(self) -> list[str]:
        return sorted(self._sources.keys() | self._callables.keys() | {"callable"})

    def source_for(self, record: SourceRecord) -> LogicSource:
        if record.name in self._callables:
            return self._callables[record.name]
        source = self._sources.get(record.kind)
        if source is None:
            raise LogicError(
                f"unknown logic source kind {record.kind!r}; known: {self.kinds()}"
            )
        return source

    def run(self, store: ObjectStore, record: SourceRecord) -> LogicResult:
        return run_logic(store, record, self.source_for(record))


def build_registry() -> LogicRegistry:
    return LogicRegistry()
