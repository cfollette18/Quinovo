from __future__ import annotations

from quinovo.chat.tools import (
    chat_tools,
    dispatch_tool,
    summarize_result,
    tool_event,
    tool_label,
)


def test_find_objects_and_get_object(client):
    kernel = client.app.state.kernel
    payload, summary = dispatch_tool(kernel, "find_objects", {"query": "1Z999"})
    assert "1Z999" in payload
    assert "Package" in summary
    payload, summary = dispatch_tool(kernel, "get_object", {"object_type": "Package", "id": "1Z999"})
    assert "1Z999" in payload
    assert "Read" in summary
    assert tool_label("get_object", {"object_type": "Package", "id": "1Z999"}) == "Read Package 1Z999"
    running = tool_event(
        "get_object",
        {"object_type": "Package", "id": "1Z999"},
        tool_id="t1",
        status="running",
    )
    assert running["calling"] == "Calling Read"
    assert running["verb"] == "Read"
    assert running["icon"] == "read"
    assert "kinds" in summarize_result(
        "list_object_types", {}, {"object_types": [{"api_name": "Package"}]}
    )


def test_chat_reuses_mcp_tools(client):
    names = {item["name"] for item in chat_tools()}
    assert "find_objects" in names
    assert "tick" in names
    assert "get_object" in names
    assert "graph" in names
    assert "apply_action" in names
    assert "remember" in names
    assert len(names) >= 40
    kernel = client.app.state.kernel
    payload, summary = dispatch_tool(kernel, "list_object_types", {})
    assert "Package" in payload
    assert "kinds" in summary
    payload, summary = dispatch_tool(kernel, "graph", {})
    assert "nodes" in payload
    assert "objects" in summary
