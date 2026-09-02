"""Quinovo as MCP: generated tools over the ontology kernel. No SQL. No PATCH."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from quinovo.kernel import Kernel


def create_mcp(kernel: Kernel) -> FastMCP:
    types = ", ".join(item.api_name for item in kernel.ontology.object_types)
    actions = ", ".join(item.api_name for item in kernel.ontology.action_types)
    sides = sorted(
        {link.from_name for link in kernel.ontology.link_types}
        | {link.to_name for link in kernel.ontology.link_types}
    )
    side_hint = ", ".join(sides) if sides else "none in this pack"
    pack_name = kernel.ontology.ontology.api_name
    mcp = FastMCP(
        "quinovo",
        instructions=(
            "Quinovo is an operational ontology. The loaded pack defines the world. "
            "Read typed objects and named links, run inference, and apply named actions only. "
            "Never PATCH or write SQL. "
            f"Pack: {pack_name}. Object types: {types}. Link sides: {side_hint}. "
            f"Actions: {actions}."
        ),
    )

    @mcp.tool(description="List object types in the loaded pack.")
    def list_object_types() -> dict[str, Any]:
        return kernel.list_object_types()

    @mcp.tool(description="Load one object by type and primary key, including inferred facts.")
    def get_object(object_type: str, id: str) -> dict[str, Any]:
        return kernel.get_object(object_type, id)

    @mcp.tool(description=f"Walk a named link side. In this pack: {side_hint}.")
    def search_around(object_type: str, id: str, side: str) -> dict[str, Any]:
        return kernel.search_around(object_type, id, side)

    @mcp.tool(
        description=(
            "List inferred facts. Unattended agents should keep status=asserted. "
            "Pending facts are HITL."
        )
    )
    def list_inferred_facts(
        object_type: str | None = None,
        id: str | None = None,
        status: str | None = "asserted",
    ) -> dict[str, Any]:
        return kernel.list_inferred_facts(object_type, id, status)

    @mcp.tool(description="Forward-chain typed inference over objects, links, and forecasts.")
    def run_inference() -> dict[str, Any]:
        return kernel.run_inference()

    @mcp.tool(description="List named actions. These are the only legal writes.")
    def list_actions() -> dict[str, Any]:
        return kernel.list_actions()

    @mcp.tool(description="Object-set read: list objects of a type, optionally by property equals.")
    def filter_objects(
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> dict[str, Any]:
        return kernel.filter_objects(object_type, property_name, equals)

    @mcp.tool(description="Read a time-series window on an object metric.")
    def get_series(object_type: str, id: str, metric: str) -> dict[str, Any]:
        return kernel.get_series(object_type, id, metric)

    @mcp.tool(description="Provenance for an inferred fact.")
    def explain_fact(fact_id: int) -> dict[str, Any]:
        return kernel.explain_fact(fact_id)

    @mcp.tool(
        description=(
            "Apply a named action from the loaded pack. Parameters follow that "
            "action's schema (object references are {parameter: {id: ...}}). "
            "Some verbs require an asserted inferred recommendation. Never PATCH a row."
        )
    )
    def apply_action(
        action_type: str,
        parameters: dict[str, Any],
        actor: str = "mcp-agent",
        fact_id: int | None = None,
    ) -> dict[str, Any]:
        return kernel.apply_action(
            action_type,
            parameters,
            actor,
            channel="mcp",
            fact_id=fact_id,
        )

    return mcp


def run_stdio(kernel: Kernel) -> None:
    create_mcp(kernel).run(transport="stdio")
