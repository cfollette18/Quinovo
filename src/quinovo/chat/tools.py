"""Workspace chat tools: the Quinovo MCP surface, plus a name search."""

from __future__ import annotations

import json
from typing import Any
from weakref import WeakKeyDictionary

from quinovo.apps.humanize import (
    fact_line,
    kind_label,
    object_name,
    status_label,
    title_case,
)
from quinovo.kernel import Kernel
from quinovo.mcp.server import create_mcp

_RESULT_CAP = 6000
_MCP: WeakKeyDictionary[Kernel, Any] = WeakKeyDictionary()

FIND_OBJECTS: dict[str, Any] = {
    "name": "find_objects",
    "description": (
        "Search objects by name or id, like Grep over the graph. "
        "Use this first when the user names something."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "object_type": {
                "type": "string",
                "description": "Optional kind to restrict the search.",
            },
        },
        "required": ["query"],
    },
}

# Cursor/Claude-style verb + icon. Unknown names fall through to Call.
_TOOL_KIND: dict[str, tuple[str, str]] = {
    "append_series": ("Write", "write"),
    "apply_action": ("Apply", "run"),
    "approve_inferred_fact": ("Approve", "approve"),
    "approve_pending_action": ("Approve", "approve"),
    "approve_proposal": ("Approve", "approve"),
    "contract": ("Read", "read"),
    "delete_action_target": ("Delete", "delete"),
    "delete_logic_source": ("Delete", "delete"),
    "delete_object": ("Delete", "delete"),
    "delete_source": ("Delete", "delete"),
    "explain_fact": ("Read", "read"),
    "filter_objects": ("Grep", "search"),
    "find_objects": ("Search", "search"),
    "get_object": ("Read", "read"),
    "get_series": ("Read", "read"),
    "graph": ("Read", "read"),
    "ingest_source": ("Write", "write"),
    "list_action_targets": ("List", "list"),
    "list_actions": ("List", "list"),
    "list_inferred_facts": ("Read", "read"),
    "list_links": ("List", "list"),
    "list_logic_sources": ("List", "list"),
    "list_object_types": ("List", "list"),
    "list_pending_actions": ("List", "list"),
    "list_proposals": ("List", "list"),
    "list_sources": ("List", "list"),
    "propose": ("Propose", "write"),
    "propose_action": ("Propose", "write"),
    "propose_pack": ("Propose", "write"),
    "propose_rule": ("Propose", "write"),
    "propose_type": ("Propose", "write"),
    "pull_source": ("Pull", "run"),
    "pull_sources": ("Pull", "run"),
    "read_pack": ("Read", "read"),
    "register_action_target": ("Write", "write"),
    "register_logic_source": ("Write", "write"),
    "register_source": ("Write", "write"),
    "reject_pending_action": ("Reject", "reject"),
    "reject_proposal": ("Reject", "reject"),
    "reload": ("Reload", "run"),
    "remember": ("Write", "write"),
    "remove_link": ("Unlink", "link"),
    "run_inference": ("Run", "run"),
    "run_logic": ("Run", "run"),
    "run_logic_source": ("Run", "run"),
    "save_turn": ("Write", "write"),
    "search_around": ("Follow", "search"),
    "set_link": ("Link", "link"),
    "tick": ("Call", "run"),
    "upsert_object": ("Write", "write"),
}

_SPECS: list[dict[str, Any]] | None = None


def _clean_schema(parameters: dict[str, Any] | None) -> dict[str, Any]:
    schema = dict(parameters or {})
    schema.pop("title", None)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return schema


def _mcp_specs() -> list[dict[str, Any]]:
    from quinovo.mcp.server import contract_registry

    specs: list[dict[str, Any]] = []
    for tool in contract_registry()._tool_manager.list_tools():
        specs.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": _clean_schema(tool.parameters),
            }
        )
    return specs


def chat_tools() -> list[dict[str, Any]]:
    """MCP tools plus find_objects. Cached — the contract does not change at runtime."""
    global _SPECS
    if _SPECS is None:
        _SPECS = [FIND_OBJECTS, *_mcp_specs()]
    return _SPECS


def anthropic_tools() -> list[dict[str, Any]]:
    return list(chat_tools())


def openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["input_schema"],
            },
        }
        for item in chat_tools()
    ]


def _clip(value: object, cap: int = 48) -> str:
    text = str(value or "").strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _kind_id(arguments: dict[str, Any]) -> str:
    kind = title_case(str(arguments.get("object_type") or ""))
    ident = str(arguments.get("id") or "")
    return f"{kind} {ident}".strip()


def _target(name: str, arguments: dict[str, Any]) -> str:
    args = arguments or {}
    match name:
        case "find_objects":
            query = _clip(args.get("query") or "")
            return f'"{query}"' if query else "the graph"
        case "get_object" | "delete_object" | "get_series" | "append_series":
            return _kind_id(args) or title_case(name)
        case "search_around":
            side = title_case(str(args.get("side") or "link"))
            host = _kind_id(args)
            return f"{side} on {host}" if host else side
        case "filter_objects":
            kind = title_case(str(args.get("object_type") or "objects"))
            prop = str(args.get("property_name") or "")
            equals = str(args.get("equals") or "")
            if prop and equals:
                return f"{kind} {prop}={_clip(equals)}"
            return kind
        case "explain_fact":
            return f"fact {args.get('fact_id')}"
        case "apply_action" | "propose_action":
            return title_case(str(args.get("action_type") or "action"))
        case "upsert_object":
            return title_case(str(args.get("object_type") or "object"))
        case "set_link" | "remove_link":
            return title_case(str(args.get("link_type") or "link"))
        case "pull_source" | "delete_source" | "run_logic_source" | "delete_logic_source" | "ingest_source":
            return str(args.get("name") or "")
        case "register_source" | "register_logic_source":
            return str(args.get("name") or args.get("kind") or "")
        case "register_action_target" | "delete_action_target":
            return title_case(str(args.get("action_type") or "target"))
        case "approve_inferred_fact":
            return f"fact {args.get('fact_id')}"
        case "approve_pending_action" | "reject_pending_action":
            return f"action {args.get('pending_id')}"
        case "approve_proposal" | "reject_proposal":
            return f"proposal {args.get('proposal_id')}"
        case "list_inferred_facts":
            if args.get("status") == "pending":
                return "items that need a look"
            host = _kind_id(args)
            return host or "inferred facts"
        case "list_proposals":
            return str(args.get("status") or "pending")
        case "propose" | "propose_pack" | "propose_rule" | "propose_type":
            return title_case(str(args.get("kind") or name.replace("propose_", "") or "change"))
        case "remember":
            return str(args.get("topic") or "memory")
        case "tick":
            return "tick"
        case "graph":
            return "graph"
        case "read_pack":
            return "pack"
        case "contract":
            return "contract"
        case "run_inference":
            return "inference"
        case "list_object_types":
            return "object types"
        case _:
            for key in ("name", "query", "id", "object_type", "action_type"):
                value = args.get(key)
                if value:
                    return _clip(value)
            return ""


def describe_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, str]:
    verb, icon = _TOOL_KIND.get(name, (title_case(name) or "Call", "call"))
    target = _target(name, arguments or {})
    label = f"{verb} {target}".strip() if target else verb
    return {
        "verb": verb,
        "icon": icon,
        "target": target,
        "label": label,
        "calling": f"Calling {verb}",
    }


def tool_label(name: str, arguments: dict[str, Any]) -> str:
    return describe_tool(name, arguments)["label"]


def tool_event(
    name: str,
    arguments: dict[str, Any],
    *,
    tool_id: str,
    status: str,
    summary: str = "",
) -> dict[str, Any]:
    spec = describe_tool(name, arguments)
    row: dict[str, Any] = {
        "type": "tool",
        "id": tool_id,
        "name": name,
        "verb": spec["verb"],
        "target": spec["target"],
        "icon": spec["icon"],
        "label": spec["label"],
        "calling": spec["calling"],
        "status": status,
    }
    if summary:
        row["summary"] = summary
    return row


def _compact(value: Any) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= _RESULT_CAP:
        return text
    return text[: _RESULT_CAP - 20] + "… [truncated]"


def _object_line(item: dict[str, Any]) -> str:
    kind = title_case(str(item.get("type") or ""))
    name = object_name(item) or str(item.get("id") or item.get("label") or "")
    if kind and name:
        return f"{kind} {name}"
    return name or kind or "an object"


def _count_key(result: dict[str, Any]) -> str | None:
    for key in (
        "objects",
        "facts",
        "proposals",
        "sources",
        "actions",
        "pending_actions",
        "links",
        "nodes",
        "object_types",
        "points",
        "logic_sources",
        "targets",
    ):
        if isinstance(result.get(key), list):
            return key
    return None


def summarize_result(name: str, arguments: dict[str, Any], result: Any) -> str:
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])
    match name:
        case "list_object_types":
            types = (result or {}).get("object_types") or []
            names = ", ".join(title_case(item.get("api_name")) for item in types[:8] if item)
            extra = f" and {len(types) - 8} more" if len(types) > 8 else ""
            return f"Found {len(types)} kinds" + (f": {names}{extra}" if names else "")
        case "find_objects":
            found = (result or {}).get("objects") or []
            if not found:
                return "Nothing matched"
            preview = ", ".join(_object_line(item) for item in found[:4])
            more = f" and {len(found) - 4} more" if len(found) > 4 else ""
            return f"Found {len(found)}: {preview}{more}"
        case "get_object":
            if not isinstance(result, dict):
                return "Read it"
            line = _object_line(result)
            facts = result.get("facts") or []
            if facts:
                first = facts[0]
                noticed = fact_line(first.get("predicate"), first.get("value"))
                return f"Read {line}. {noticed}"
            return f"Read {line}"
        case "search_around":
            objects = (result or {}).get("objects") or []
            if not objects:
                return "No connections that way"
            return "Connected to " + ", ".join(_object_line(item) for item in objects[:6])
        case "filter_objects":
            objects = (result or {}).get("objects") or []
            kind = title_case(str(arguments.get("object_type") or "object"))
            return f"Found {len(objects)} {kind}"
        case "list_inferred_facts":
            facts = (result or {}).get("facts") or []
            pending = sum(1 for item in facts if item.get("status") == "pending")
            if pending:
                return f"{len(facts)} facts, {pending} still need a look"
            return f"{len(facts)} facts"
        case "explain_fact":
            if not isinstance(result, dict):
                return "Looked up the fact"
            return fact_line(result.get("predicate"), result.get("value")) or "Explained the fact"
        case "list_actions":
            actions = (result or {}).get("actions") or []
            return f"{len(actions)} named actions"
        case "list_pending_actions":
            rows = (result or {}).get("pending_actions") or (result or {}).get("actions") or []
            return "Nothing queued" if not rows else f"{len(rows)} waiting on approval"
        case "list_proposals":
            rows = (result or {}).get("proposals") or []
            if not rows:
                return "Nothing waiting"
            first = rows[0]
            label = first.get("title") or kind_label(str(first.get("kind") or ""))
            return f"{len(rows)} proposals, including {label}"
        case "list_sources":
            rows = (result or {}).get("sources") or []
            return f"{len(rows)} sources"
        case "get_series":
            points = (result or {}).get("points") or (result or {}).get("series") or []
            return f"{len(points)} points"
        case "apply_action":
            status = (result or {}).get("status") or "applied"
            return status_label(str(status)) or title_case(str(status))
        case "propose_action":
            status = (result or {}).get("status") or "pending"
            return status_label(str(status)) or "Parked for a look"
        case "graph":
            nodes = (result or {}).get("nodes") or []
            edges = (result or {}).get("edges") or []
            return f"{len(nodes)} objects, {len(edges)} links"
        case "tick":
            return "Loop finished"
        case "run_inference":
            facts = (result or {}).get("facts") or (result or {}).get("inferred") or []
            if isinstance(facts, list):
                return f"{len(facts)} facts"
            return "Inference finished"
        case "read_pack":
            docs = (result or {}).get("documents") or (result or {}).get("files") or []
            if isinstance(docs, list) and docs:
                return f"{len(docs)} pack files"
            return "Read the pack"
        case _:
            if not isinstance(result, dict):
                return "Done"
            key = _count_key(result)
            if key:
                label = key.replace("_", " ")
                return f"{len(result[key])} {label}"
            status = result.get("status")
            if status:
                return status_label(str(status)) or title_case(str(status))
            if result.get("ok"):
                return "Done"
            return "Done"


def _find_objects(kernel: Kernel, query: str, object_type: str | None = None) -> dict[str, Any]:
    needle = query.strip().lower()
    graph = kernel.graph()
    hits: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if object_type and str(node.get("type") or "") != object_type:
            continue
        blob = f"{node.get('id', '')} {node.get('label', '')} {node.get('pk', '')}".lower()
        if needle and needle not in blob:
            continue
        hits.append(
            {
                "type": node.get("type"),
                "id": node.get("pk") or str(node.get("id") or "").split(":", 1)[-1],
                "label": node.get("label"),
            }
        )
        if len(hits) >= 40:
            break
    return {"objects": hits, "count": len(hits)}


def _mcp_for(kernel: Kernel) -> Any:
    cached = _MCP.get(kernel)
    if cached is None:
        cached = create_mcp(kernel)
        _MCP[kernel] = cached
    return cached


def _invoke(tool: Any, arguments: dict[str, Any]) -> Any:
    meta = tool.fn_metadata
    pre = meta.pre_parse_json(arguments or {})
    parsed = meta.arg_model.model_validate(pre)
    kwargs = parsed.model_dump_one_level()
    return tool.fn(**kwargs)


def dispatch_tool(kernel: Kernel, name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    """Run a chat tool. Returns (model_payload, ui_summary)."""
    args = dict(arguments or {})
    try:
        if name == "find_objects":
            result = _find_objects(kernel, str(args.get("query") or ""), args.get("object_type"))
        elif name == "apply_action":
            result = kernel.apply_action(
                str(args.get("action_type") or ""),
                args.get("parameters") or {},
                actor=str(args.get("actor") or "workspace-chat"),
                channel="human",
                fact_id=args.get("fact_id"),
            )
        else:
            tool = _mcp_for(kernel)._tool_manager.get_tool(name)
            if tool is None:
                err = f"Unknown step {name}"
                return json.dumps({"error": err}), err
            result = _invoke(tool, args)
    except TypeError as exc:
        err = f"That step needed different details: {exc}"
        return json.dumps({"error": err}), err
    except (KeyError, ValueError, PermissionError, FileNotFoundError) as exc:
        err = str(exc)
        return json.dumps({"error": err}), err
    except Exception as exc:
        err = str(exc)[:240]
        return json.dumps({"error": err}), err
    summary = summarize_result(name, args, result)
    return _compact(result), summary
