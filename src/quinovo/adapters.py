"""Same tool contract for MCP, Hermes, and Google ADK. Quinovo is not an agent."""

from __future__ import annotations

from typing import Any


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_object_types",
            "description": "List object types in the loaded pack.",
        },
        {
            "name": "get_object",
            "description": "Load one object by type and primary key, including inferred facts.",
        },
        {
            "name": "search_around",
            "description": "Walk a named link side defined by the loaded pack.",
        },
        {
            "name": "filter_objects",
            "description": "Object-set read: list objects of a type, optionally by property equals.",
        },
        {
            "name": "list_inferred_facts",
            "description": "List inferred facts. Unattended agents should keep status=asserted.",
        },
        {
            "name": "run_inference",
            "description": "Forward-chain typed inference over objects, links, and forecasts.",
        },
        {
            "name": "list_actions",
            "description": "List named actions. These are the only legal writes.",
        },
        {
            "name": "apply_action",
            "description": "Apply a named action. Never PATCH a row.",
        },
        {
            "name": "get_series",
            "description": "Read a time-series window on an object metric.",
        },
        {
            "name": "explain_fact",
            "description": "Provenance for an inferred fact: rule, premises, forecast if any.",
        },
    ]


def hermes_skill() -> dict[str, Any]:
    return {
        "name": "quinovo",
        "description": "Operational ontology. Read typed links, infer, apply_action only.",
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
        "    return [",
        "        FunctionTool(list_object_types),",
        "        FunctionTool(get_object),",
        "        FunctionTool(search_around),",
        "        FunctionTool(run_inference),",
        "        FunctionTool(apply_action),",
        "    ]",
        "",
    ]
    return "\n".join(lines)
