from __future__ import annotations

import json
from typing import Any

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

from quinovo.kernel import Kernel, open_kernel
from quinovo.mcp.server import create_mcp

EXPECTED_TOOLS = {
    "list_object_types",
    "get_object",
    "search_around",
    "filter_objects",
    "list_inferred_facts",
    "run_inference",
    "list_actions",
    "apply_action",
    "get_series",
    "explain_fact",
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
    assert "sql" not in {n.lower() for n in names}
    assert not any("patch" in n.lower() for n in names)


def test_mcp_reads_bob_via_named_link(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    box = _mcp(kernel, "get_object", {"object_type": "Package", "id": "1Z999"})
    assert box["id"] == "1Z999"
    buyer = _mcp(
        kernel,
        "search_around",
        {"object_type": "Package", "id": "1Z999", "side": "buyer"},
    )
    assert buyer["objects"][0]["id"] == "bob"


def test_mcp_notify_buyer_requires_asserted_recommendation(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
    message = _mcp_error(
        kernel,
        "apply_action",
        {
            "action_type": "notify_buyer",
            "parameters": {"package": {"id": "1Z999"}},
        },
    )
    assert "asserted recommended_action" in message
    box = kernel.get_object("Package", "1Z999")
    assert "buyer_notified" not in box["properties"]


def test_mcp_forecast_infer_notify_loop(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "mcp.sqlite")
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
            "parameters": {"package": {"id": "1Z999"}},
            "actor": "cursor-agent",
        },
    )
    assert applied["result"] == "applied"
    assert applied["objects"][0]["properties"]["buyer_notified"] == "true"
    assert applied["parameters"]["fact_id"] == rec["id"]
