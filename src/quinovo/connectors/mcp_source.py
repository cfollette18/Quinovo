"""MCP source: another MCP server (or any JSON-RPC tool endpoint) is the connector.

Quinovo does not ship a catalog of vendor adapters. It calls a listed tool
over HTTP JSON-RPC, or a one-shot stdio command, and maps the result to
objects. That is the whole connector story.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import httpx

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.connectors.mapping import extract_rows, upsert_rows
from quinovo.engine.store import ObjectStore


class McpSource:
    """Call one tool on a remote MCP/JSON-RPC endpoint and upsert the rows.

    config:
        url: str            — HTTP JSON-RPC endpoint (transport=http, default).
        command: str|list   — stdio command (transport=stdio).
        tool / tool_name:   — tool to call.
        arguments: dict     — optional tool arguments.
        rows_path: str      — optional dotted path into the result.
        headers: dict       — optional HTTP headers. Never log these.
        transport: str      — ``http`` (default) or ``stdio``.
    """

    kind = "mcp"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        transport = str(record.config.get("transport") or "http").lower()
        match transport:
            case "http":
                payload = _call_http(record)
            case "stdio":
                payload = _call_stdio(record)
            case _ as other:
                raise ConnectorError(f"unknown mcp transport {other!r}")
        rows_path = record.config.get("rows_path")
        path = rows_path if isinstance(rows_path, str) and rows_path else None
        rows = _rows_from_mcp(payload, path)
        return upsert_rows(store, record, rows, f"{len(rows)} rows from the MCP tool")


def mcp_request(record: SourceRecord) -> dict[str, Any]:
    """JSON-RPC body for ``tools/call`` (also used by action write-back)."""
    tool = record.config.get("tool") or record.config.get("tool_name")
    if not isinstance(tool, str) or not tool:
        raise ConnectorError("mcp source needs a tool name")
    arguments = record.config.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ConnectorError("mcp source arguments must be a mapping")
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": record.config.get("method") or "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


def _call_http(record: SourceRecord) -> Any:
    url = record.config.get("url")
    if not isinstance(url, str) or not url:
        raise ConnectorError("mcp source needs a URL (or use transport=stdio)")
    headers = record.config.get("headers") or {}
    if not isinstance(headers, dict):
        raise ConnectorError("mcp source headers must be a mapping")
    try:
        response = httpx.post(url, json=mcp_request(record), headers=headers, timeout=15.0)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise ConnectorError(f"mcp tool call failed: {exc}") from exc


def _call_stdio(record: SourceRecord) -> Any:
    raw = record.config.get("command")
    if isinstance(raw, str) and raw.strip():
        command = raw.strip()
        argv = ["sh", "-c", command]
    elif isinstance(raw, list) and raw:
        argv = [str(part) for part in raw]
    else:
        raise ConnectorError("mcp stdio source needs a command")
    try:
        completed = subprocess.run(
            argv,
            input=json.dumps(mcp_request(record)),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        raise ConnectorError(f"mcp stdio call failed: {exc}") from exc
    if completed.returncode != 0:
        raise ConnectorError("mcp stdio command exited with an error")
    text = (completed.stdout or "").strip()
    if not text:
        raise ConnectorError("mcp stdio command returned nothing")
    try:
        return json.loads(text.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise ConnectorError("mcp stdio command did not return JSON") from exc


def _rows_from_mcp(payload: Any, rows_path: str | None) -> list[Any]:
    """Accept a JSON-RPC result, a structured MCP envelope, or a plain list."""
    result = payload
    if isinstance(payload, dict) and "result" in payload:
        result = payload["result"]
    if isinstance(result, dict) and isinstance(result.get("structuredContent"), dict):
        result = result["structuredContent"]
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        for item in result["content"]:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    rows = extract_rows(parsed, rows_path, singleton=True)
                    if rows:
                        return rows
    return extract_rows(result, rows_path, singleton=True)
