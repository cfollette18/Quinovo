"""External logic layer: logic can live anywhere and feed the ontology.

Quinovo already has typed inference rules and forecasts. This package makes the
logic layer *composable and external*: a logic source is a function, an HTTP
endpoint, or an MCP tool that produces inferred facts or forecasts and writes
them into the ontology. Logic does not have to live in YAML rules.
"""

from __future__ import annotations

from quinovo.logic.base import LogicError, LogicResult, LogicSource, SourceRecord, run_logic
from quinovo.logic.registry import LogicRegistry, build_registry

__all__ = [
    "LogicError",
    "LogicRegistry",
    "LogicResult",
    "LogicSource",
    "SourceRecord",
    "build_registry",
    "run_logic",
]
