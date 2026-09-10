"""Kind catalog for the Connections page: logos, blurbs, and form fields.

No raw JSON. Each kind is a card a person can pick, then a short form.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quinovo.connectors.mapping import parse_property_map


@dataclass(frozen=True)
class ConnectionKind:
    id: str
    layer: str  # data | action
    name: str
    blurb: str
    icon: str


_ICON = {
    "http": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M4 12h16M12 4c2.5 2.8 2.5 13.2 0 16M12 4c-2.5 2.8-2.5 13.2 0 16" '
        'fill="none" stroke="currentColor" stroke-width="1.6"/></svg>'
    ),
    "json": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<path d="M8 6c-2 0-3 1.4-3 6s1 6 3 6M16 6c2 0 3 1.4 3 6s-1 6-3 6" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '<circle cx="12" cy="12" r="1.4" fill="currentColor"/></svg>'
    ),
    "csv": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<rect x="5" y="4" width="14" height="16" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M5 9h14M5 14h14M10 4v16M15 4v16" stroke="currentColor" stroke-width="1.4"/></svg>'
    ),
    "webhook": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<path d="M7 15a4 4 0 1 1 1.2-7.8M17 9a4 4 0 1 1-1.2 7.8M9.5 14.5 14.5 9.5" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
    ),
    "sql": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<ellipse cx="12" cy="7" rx="7" ry="3" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M5 7v10c0 1.7 3.1 3 7 3s7-1.3 7-3V7" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '</svg>'
    ),
    "mcp": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<circle cx="6" cy="12" r="2.4" fill="currentColor"/>'
        '<circle cx="18" cy="12" r="2.4" fill="currentColor"/>'
        '<path d="M8.4 12h7.2" stroke="currentColor" stroke-width="1.8"/></svg>'
    ),
    "youtube": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<rect x="3.5" y="6" width="17" height="12" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linejoin="miter"/>'
        '<path d="M10 9.2v5.6L16 12z" fill="currentColor"/></svg>'
    ),
    "email": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<rect x="3.5" y="6" width="17" height="12" fill="none" stroke="currentColor" stroke-width="1.8"/>'
        '<path d="M4 7l8 6 8-6" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>'
    ),
    "slack": (
        '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
        '<path d="M8 3v4M16 17v4M3 8h4M17 16h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>'
        '<rect x="7" y="7" width="4" height="4" fill="currentColor"/>'
        '<rect x="13" y="13" width="4" height="4" fill="currentColor"/>'
        '<rect x="13" y="7" width="4" height="4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<rect x="7" y="13" width="4" height="4" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '</svg>'
    ),
}


DATA_KINDS: tuple[ConnectionKind, ...] = (
    ConnectionKind(
        "youtube",
        "data",
        "YouTube",
        "Paste a video address. Quinovo reads the captions and files the useful claims.",
        _ICON["youtube"],
    ),
    ConnectionKind("http", "data", "Web address", "Pull a list of things from any site that speaks HTTP.", _ICON["http"]),
    ConnectionKind("json", "data", "JSON feed", "Poll a public list and turn each item into an object.", _ICON["json"]),
    ConnectionKind("csv", "data", "Spreadsheet", "Read a CSV file on this machine.", _ICON["csv"]),
    ConnectionKind("webhook", "data", "Incoming push", "Give other systems an address they can POST to.", _ICON["webhook"]),
    ConnectionKind("sql", "data", "Database", "Run a read-only query. SQLite always; Postgres if a driver is installed.", _ICON["sql"]),
    ConnectionKind("mcp", "data", "MCP", "Call a tool on another MCP server. That is the connector.", _ICON["mcp"]),
)

ACTION_KINDS: tuple[ConnectionKind, ...] = (
    ConnectionKind("webhook", "action", "Webhook", "POST the applied action to any HTTP address.", _ICON["webhook"]),
    ConnectionKind("slack", "action", "Slack", "Send a short message to a Slack incoming webhook.", _ICON["slack"]),
    ConnectionKind("email", "action", "Email", "Send mail over SMTP, or log the message if mail is not set up.", _ICON["email"]),
    ConnectionKind("mcp", "action", "MCP", "Call a tool on a connected MCP endpoint when the action applies.", _ICON["mcp"]),
    ConnectionKind("sql", "action", "Database write", "A gated, audited INSERT or UPDATE on an allow-listed table.", _ICON["sql"]),
)


def kind_by_id(kind_id: str, layer: str) -> ConnectionKind | None:
    catalog = DATA_KINDS if layer == "data" else ACTION_KINDS
    for item in catalog:
        if item.id == kind_id:
            return item
    return None


def icon_for(kind: str) -> str:
    return _ICON.get(kind, _ICON["mcp"])


def config_from_data_form(kind: str, fields: dict[str, str]) -> dict[str, Any]:
    """Build a source config from human form fields. Never accepts a JSON blob."""
    mapping = parse_property_map(fields.get("property_map") or "")
    id_field = (fields.get("id_field") or "").strip()
    token = (fields.get("token") or "").strip()
    config: dict[str, Any] = {}
    match kind:
        case "http" | "json":
            config["url"] = (fields.get("url") or "").strip()
            rows_path = (fields.get("rows_path") or "").strip()
            if rows_path:
                config["rows_path"] = rows_path
            if token:
                config["headers"] = {"Authorization": f"Bearer {token}"}
        case "csv":
            config["path"] = (fields.get("path") or "").strip()
        case "webhook":
            if token:
                config["token"] = token
            rows_path = (fields.get("rows_path") or "").strip()
            if rows_path:
                config["rows_path"] = rows_path
        case "sql":
            config["dsn"] = (fields.get("dsn") or fields.get("path") or "").strip()
            config["query"] = (fields.get("query") or "").strip()
        case "mcp":
            url = (fields.get("url") or "").strip()
            command = (fields.get("command") or "").strip()
            if url:
                config["url"] = url
            if command:
                config["command"] = command
                config["transport"] = "stdio"
            config["tool"] = (fields.get("tool") or "").strip()
            if token:
                config["headers"] = {"Authorization": f"Bearer {token}"}
        case "youtube":
            config["url"] = (fields.get("url") or "").strip()
            topic = (fields.get("topic") or "").strip()
            if topic:
                config["topic"] = topic
        case "synthetic":
            config["rows"] = []
        case _ as other:
            raise ValueError(f"unknown source kind {other!r}")
    if kind != "youtube":
        if mapping:
            config["property_map"] = mapping
        if id_field:
            config["id_field"] = id_field
    return config


def config_from_action_form(kind: str, fields: dict[str, str]) -> dict[str, Any]:
    token = (fields.get("token") or "").strip()
    match kind:
        case "webhook" | "http":
            config: dict[str, Any] = {"url": (fields.get("url") or "").strip()}
            if token:
                config["headers"] = {"Authorization": f"Bearer {token}"}
            return config
        case "slack":
            return {"url": (fields.get("url") or "").strip()}
        case "email":
            return {
                "to": (fields.get("to") or "").strip(),
                "smtp_host": (fields.get("smtp_host") or "").strip(),
                "smtp_user": (fields.get("smtp_user") or "").strip(),
                "smtp_password": (fields.get("smtp_password") or "").strip(),
                "from": (fields.get("from_addr") or "").strip(),
            }
        case "mcp":
            mcp_config: dict[str, Any] = {
                "url": (fields.get("url") or "").strip(),
                "tool": (fields.get("tool") or "").strip(),
            }
            if token:
                mcp_config["headers"] = {"Authorization": f"Bearer {token}"}
            return mcp_config
        case "sql":
            tables = [
                part.strip()
                for part in (fields.get("allowed_tables") or "").split(",")
                if part.strip()
            ]
            return {
                "dsn": (fields.get("dsn") or "").strip(),
                "statement": (fields.get("statement") or "").strip(),
                "allow_write": True,
                "allowed_tables": tables,
            }
        case _ as other:
            raise ValueError(f"unknown target kind {other!r}")
