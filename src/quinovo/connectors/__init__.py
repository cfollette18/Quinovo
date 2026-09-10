"""Quinovo connectors: data flows into the ontology through MCP-style sources.

A *source* is a connector that pulls external data into the kernel as ontology
objects. Quinovo does not ship a 300-connector marketplace. The connector layer
*is* MCP: any MCP-compatible client can wire a real system, and Quinovo also
exposes itself as MCP. The built-in sources here are honest, shippable patterns
(HTTP, CSV, inbound webhook, SQL, MCP, JSON feed, YouTube captions, agent transcripts, plus a synthetic generator)
so an agent can wire real systems without a proprietary marketplace.
"""

from __future__ import annotations

from quinovo.connectors.base import Connector, ConnectorError, SourceRecord, run_source
from quinovo.connectors.registry import ConnectorRegistry, build_registry

__all__ = [
    "Connector",
    "ConnectorError",
    "ConnectorRegistry",
    "SourceRecord",
    "build_registry",
    "run_source",
]
