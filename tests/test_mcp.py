from __future__ import annotations

import json
from typing import Any

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

from conftest import EXAMPLE_PACK
from quinovo.kernel import Kernel, open_kernel
from quinovo.mcp.contract import tool_specs
from quinovo.mcp.server import create_mcp

EXPECTED_TOOLS = {
    "tick",
    "briefing",
    "about",
    "recall",
    "remember",
    "save_turn",
    "list_object_types",
    "get_object",
    "search_around",
    "filter_objects",
    "list_links",
    "list_inferred_facts",
    "run_inference",
    "explain_fact",
    "list_actions",
    "apply_action",
    "get_series",
    "append_series",
    "upsert_object",
    "delete_object",
    "set_link",
    "remove_link",
    "read_pack",
    "propose",
    "propose_pack",
    "propose_rule",
    "propose_type",
    "reload",
    "approve_inferred_fact",
    "list_pending_actions",
    "approve_pending_action",
    "reject_pending_action",
    "list_proposals",
    "approve_proposal",
    "reject_proposal",
    "graph",
    "list_sources",
    "register_source",
    "pull_source",
    "pull_sources",
    "delete_source",
    "ingest_source",
    "list_logic_sources",
    "register_logic_source",
    "run_logic_source",
    "run_logic",
    "delete_logic_source",
    "list_action_targets",
    "register_action_target",
    "delete_action_target",
    "propose_action",
    "contract",
}


def _text(result) -> str:
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _body(result) -> dict[str, Any]:
    if result.structuredContent:
        return result.structuredContent
    return json.loads(_text(result))


def _mcp(kernel: Kernel, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    server = create_mcp(kernel)

    async def call() -> dict[str, Any]:
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(name, arguments or {})
            if result.isError:
                raise AssertionError(_text(result) or "mcp tool error")
            return _body(result)

    return anyio.run(call)


def _mcp_error(kernel: Kernel, name: str, arguments: dict[str, Any]) -> str:
    server = create_mcp(kernel)

    async def call() -> str:
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(name, arguments)
            assert result.isError
            return _text(result)

    return anyio.run(call)


def test_mcp_tool_list(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    server = create_mcp(kernel)

    async def listed() -> set[str]:
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            return {tool.name for tool in tools.tools}

    names = anyio.run(listed)
    assert names == EXPECTED_TOOLS
    assert {spec["name"] for spec in tool_specs()} == EXPECTED_TOOLS
    assert "sql" not in {n.lower() for n in names}
    assert not any("patch" in n.lower() for n in names)
    assert "write_ontology" not in names
    assert "write_inference" not in names
    assert "create_pack" not in names


def test_mcp_reads_bob_via_named_link(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    box = _mcp(kernel, "get_object", {"object_type": "Package", "id": "1Z999"})
    assert box["id"] == "1Z999"
    buyer = _mcp(
        kernel,
        "search_around",
        {"object_type": "Package", "id": "1Z999", "side": "buyer"},
    )
    assert buyer["objects"][0]["id"] == "bob"


def test_mcp_notify_buyer_requires_asserted_recommendation(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    message = _mcp_error(
        kernel,
        "apply_action",
        {
            "action_type": "notify_buyer",
            "parameters": {"package": {"type": "Package", "id": "1Z999"}},
        },
    )
    assert "asserted recommended_action" in message
    box = kernel.get_object("Package", "1Z999")
    assert "buyer_notified" not in box["properties"]


def test_mcp_forecast_infer_notify_loop(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    kernel.write_forecast(
        "Package",
        "1Z999",
        "late_risk",
        24,
        0.4,
        "timesfm-2.5",
        0.88,
    )
    inferred = _mcp(kernel, "run_inference")
    predicates = {fact["predicate"] for fact in inferred["facts"]}
    assert "at_risk" in predicates
    assert "recommended_action" in predicates
    rec = next(f for f in inferred["facts"] if f["predicate"] == "recommended_action")
    assert rec["status"] == "asserted"
    assert "bob" in rec["value"]

    applied = _mcp(
        kernel,
        "apply_action",
        {
            "action_type": "notify_buyer",
            "parameters": {"package": {"type": "Package", "id": "1Z999"}},
            "actor": "cursor-agent",
        },
    )
    assert applied["result"] == "applied"
    assert applied["objects"][0]["properties"]["buyer_notified"] == "true"
    assert applied["parameters"]["fact_id"] == rec["id"]


def test_mcp_propose_rule_is_hitl(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    body = _mcp(
        kernel,
        "propose_rule",
        {
            "rule": {
                "api_name": "synth_test_late",
                "kind": "property_fact",
                "description": "test",
                "source_type": "Package",
                "confidence": 0.9,
                "when_property": {"api_name": "status", "equals": "lost"},
                "then_fact": {"predicate": "lost", "value": "true"},
            },
            "confidence": 0.4,
        },
    )
    assert body["hitl"] is True
    assert body["proposal"]["status"] == "pending"
    listed = _mcp(kernel, "list_proposals", {"status": "pending"})
    assert listed["proposals"]


def test_mcp_tick_returns_hitl_surface(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    body = _mcp(kernel, "tick")
    assert "pending_proposals" in body
    assert "pending_facts" in body
    assert "pending_actions" in body
    assert "sources_pulled" in body
    assert "logic_ran" in body


def test_mcp_register_and_pull_source(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    body = _mcp(
        kernel,
        "register_source",
        {
            "name": "feed",
            "kind": "synthetic",
            "object_type": "Package",
            "config": {"rows": [{"id": "MCP1", "status": "in_transit"}]},
        },
    )
    assert body["name"] == "feed"
    pulled = _mcp(kernel, "pull_source", {"name": "feed"})
    assert pulled["count"] == 1
    obj = _mcp(kernel, "get_object", {"object_type": "Package", "id": "MCP1"})
    assert obj["properties"]["status"] == "in_transit"


def test_mcp_register_logic_source(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    body = _mcp(
        kernel,
        "register_logic_source",
        {"name": "logic", "kind": "http", "config": {"url": "https://example.invalid/x"}},
    )
    assert body["name"] == "logic"
    listed = _mcp(kernel, "list_logic_sources")
    assert listed["logic_sources"]


def test_mcp_register_action_target(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    body = _mcp(
        kernel,
        "register_action_target",
        {"action_type": "mark_delivered", "kind": "webhook", "config": {"url": "https://x.invalid/h"}},
    )
    assert body["action_type"] == "mark_delivered"
    listed = _mcp(kernel, "list_action_targets")
    assert listed["targets"]


def test_mcp_propose_action_is_hitl(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "mcp.sqlite")
    body = _mcp(
        kernel,
        "propose_action",
        {
            "action_type": "mark_delivered",
            "parameters": {"package": {"type": "Package", "id": "1Z999"}},
            "confidence": 0.4,
            "reason": "late",
        },
    )
    assert body["hitl"] is True
    assert body["proposal"]["kind"] == "action_application"


def test_mcp_contract_returns_sdk_surface(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    body = _mcp(kernel, "contract")
    assert "mcp" in body
    assert "hermes" in body
    assert "adk" in body
