"""Same tool contract for MCP, Hermes, and Google ADK. Quinovo is not an agent."""

from __future__ import annotations

from typing import Any


def tool_specs() -> list[dict[str, Any]]:
    """Derived from the FastMCP registry so the contract cannot drift from mcp/server.py."""
    from quinovo.mcp.server import contract_registry

    return [
        {"name": tool.name, "description": tool.description or ""}
        for tool in contract_registry()._tool_manager.list_tools()
    ]


def hermes_skill() -> dict[str, Any]:
    return {
        "name": "quinovo",
        "description": (
            "Operational ontology. It ticks itself in the background — never "
            "ask for 'quinovo tick'. Call remember at the end of every turn "
            "with the raw text (save_turn only when already structured). "
            "Propose packs and rules; humans only approve HITL. "
            "Read/write objects and links."
        ),
        "tools": tool_specs(),
    }


def adk_function_tools() -> str:
    lines = [
        '"""Google ADK FunctionTools generated from the Quinovo ontology contract.',
        "Wire these to quinovo.kernel.Kernel. Do not give the model SQL.",
        '"""',
        "from google.adk.tools import FunctionTool",
        "",
        "def quinovo_adk_tools(kernel):",
        "    def tick(actor: str = 'autonomous'):",
        "        return kernel.tick(actor)",
        "    def remember(text: str, topic: str = 'quinovo', session_id: str = 'autonomous', actor: str = 'adk-agent'):",
        "        return kernel.remember(text, topic=topic, session_id=session_id, actor=actor)",
        "    def list_object_types():",
        "        return kernel.list_object_types()",
        "    def get_object(object_type: str, id: str):",
        "        return kernel.get_object(object_type, id)",
        "    def search_around(object_type: str, id: str, side: str):",
        "        return kernel.search_around(object_type, id, side)",
        "    def apply_action(action_type: str, parameters: dict, actor: str = 'adk-agent'):",
        "        return kernel.apply_action(action_type, parameters, actor, channel='mcp')",
        "    def run_inference():",
        "        return kernel.run_inference()",
        "    def propose_rule(rule: dict, confidence: float, actor: str = 'adk-agent'):",
        "        return kernel.propose('inference_rule', rule, confidence, actor)",
        "    def approve_proposal(proposal_id: int, actor: str = 'human'):",
        "        return kernel.approve_proposal(proposal_id, actor)",
        "    return [",
        "        FunctionTool(tick),",
        "        FunctionTool(remember),",
        "        FunctionTool(list_object_types),",
        "        FunctionTool(get_object),",
        "        FunctionTool(search_around),",
        "        FunctionTool(run_inference),",
        "        FunctionTool(apply_action),",
        "        FunctionTool(propose_rule),",
        "        FunctionTool(approve_proposal),",
        "    ]",
        "",
    ]
    return "\n".join(lines)
