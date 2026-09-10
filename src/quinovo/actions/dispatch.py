"""Action write-back: applying an action can drive a real change in an external system.

An action target is bound to an action type. When an action is *applied*
(after the approval gate and after local edits succeed), the dispatcher fires
the target and records the result in the audit log. Failures never undo the
local apply — the ontology is the system of record. Pending actions do not
fire a target.
"""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from quinovo.engine.sql import execute_write, open_sql_connection
from quinovo.engine.store import ActionTargetRecord, AuditRow, ObjectStore

TARGET_KINDS = ("webhook", "http", "email", "slack", "mcp", "sql")

_WRITE_OK = re.compile(
    r"^\s*(INSERT\s+INTO|UPDATE)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


class DispatchError(Exception):
    """A write-back target could not be reached or rejected the call."""


def dispatch(
    store: ObjectStore,
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    """Fire one write-back target. Returns a result payload for the audit log."""
    del store
    if not target.enabled:
        raise DispatchError("this write-back is paused")
    match target.kind:
        case "webhook" | "http":
            return _dispatch_http(target, action_type, parameters, audit)
        case "slack":
            return _dispatch_slack(target, action_type, parameters, audit)
        case "email":
            return _dispatch_email(target, action_type, parameters, audit)
        case "mcp":
            return _dispatch_mcp(target, action_type, parameters, audit)
        case "sql":
            return _dispatch_sql(target, action_type, parameters, audit)
        case _ as unreachable:
            raise DispatchError(f"unknown target kind {unreachable!r}")


def _payload(
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "parameters": parameters,
        "audit_id": audit.id,
        "actor": audit.actor,
        "created_at": audit.created_at,
    }


def _headers(config: dict[str, Any]) -> dict[str, str]:
    headers = config.get("headers") or {}
    if not isinstance(headers, dict):
        raise DispatchError("headers must be a mapping")
    return {str(key): str(value) for key, value in headers.items()}


def _dispatch_http(
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    url = target.config.get("url")
    if not isinstance(url, str) or not url:
        raise DispatchError("http target needs a URL")
    body = _payload(action_type, parameters, audit)
    try:
        response = httpx.post(url, json=body, headers=_headers(target.config), timeout=15.0)
        status = response.status_code
        ok = 200 <= status < 300
        try:
            payload: Any = response.json()
        except Exception:  # noqa: BLE001
            payload = response.text[:500]
    except Exception as exc:
        raise DispatchError(f"write-back failed: {exc}") from exc
    if not ok:
        raise DispatchError(f"write-back returned {status}")
    return {"target": target.kind, "url": url, "status": status, "response": payload}


def _dispatch_slack(
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    url = target.config.get("url")
    if not isinstance(url, str) or not url:
        raise DispatchError("slack target needs an incoming webhook URL")
    text = target.config.get("text") or _human_action_line(action_type, parameters)
    body = {"text": text}
    try:
        response = httpx.post(url, json=body, headers=_headers(target.config), timeout=15.0)
        status = response.status_code
        ok = 200 <= status < 300
    except Exception as exc:
        raise DispatchError(f"slack write-back failed: {exc}") from exc
    if not ok:
        raise DispatchError(f"slack write-back returned {status}")
    return {"target": "slack", "status": status, "text": text, "audit_id": audit.id}


def _dispatch_email(
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    to = target.config.get("to")
    if not isinstance(to, str) or not to:
        raise DispatchError("email target needs a to address")
    subject = str(target.config.get("subject") or f"Quinovo: {action_type}")
    body = str(target.config.get("body") or _human_action_line(action_type, parameters))
    host = target.config.get("smtp_host")
    if not isinstance(host, str) or not host:
        return {
            "target": "email",
            "mode": "logged",
            "to": to,
            "subject": subject,
            "audit_id": audit.id,
        }
    message = EmailMessage()
    message["To"] = to
    message["From"] = str(target.config.get("from") or "quinovo@localhost")
    message["Subject"] = subject
    message.set_content(body)
    port = int(target.config.get("smtp_port") or 587)
    user = target.config.get("smtp_user")
    password = target.config.get("smtp_password")
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            if isinstance(user, str) and user:
                smtp.login(user, str(password or ""))
            smtp.send_message(message)
    except Exception as exc:
        raise DispatchError(f"email send failed: {exc}") from exc
    return {"target": "email", "mode": "smtp", "to": to, "subject": subject, "audit_id": audit.id}


def _dispatch_mcp(
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    url = target.config.get("url")
    if not isinstance(url, str) or not url:
        raise DispatchError("mcp target needs a URL")
    tool = target.config.get("tool") or target.config.get("tool_name")
    if not isinstance(tool, str) or not tool:
        raise DispatchError("mcp target needs a tool name")
    arguments = target.config.get("arguments") or _payload(action_type, parameters, audit)
    if not isinstance(arguments, dict):
        raise DispatchError("mcp target arguments must be a mapping")
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": target.config.get("method") or "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    try:
        response = httpx.post(url, json=body, headers=_headers(target.config), timeout=15.0)
        status = response.status_code
        ok = 200 <= status < 300
        try:
            payload: Any = response.json()
        except Exception:  # noqa: BLE001
            payload = response.text[:500]
    except Exception as exc:
        raise DispatchError(f"mcp write-back failed: {exc}") from exc
    if not ok:
        raise DispatchError(f"mcp write-back returned {status}")
    return {"target": "mcp", "tool": tool, "status": status, "response": payload}


def _dispatch_sql(
    target: ActionTargetRecord,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    if not target.config.get("allow_write"):
        raise DispatchError("sql write is gated — set allow_write to turn it on")
    statement = target.config.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise DispatchError("sql target needs a statement")
    match = _WRITE_OK.match(statement)
    if match is None:
        raise DispatchError("sql write only allows INSERT or UPDATE")
    table = match.group(2)
    allowed = target.config.get("allowed_tables") or []
    if isinstance(allowed, str):
        allowed = [part.strip() for part in allowed.split(",") if part.strip()]
    if not isinstance(allowed, list) or not allowed:
        raise DispatchError("sql write needs an allowed_tables list")
    if table not in {str(item) for item in allowed}:
        raise DispatchError("that table is not on the allow-list")
    dsn = target.config.get("dsn") or target.config.get("path")
    if not isinstance(dsn, str) or not dsn:
        raise DispatchError("sql target needs a database path or connection URL")
    binds = _sql_binds(action_type, parameters, audit)
    try:
        conn = open_sql_connection(dsn)
        try:
            changed = execute_write(conn, statement, binds)
        finally:
            conn.close()
    except DispatchError:
        raise
    except Exception as exc:
        raise DispatchError("sql write failed") from exc
    return {"target": "sql", "table": table, "changed": changed, "audit_id": audit.id}


def _sql_binds(
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
) -> dict[str, Any]:
    binds: dict[str, Any] = {
        "action_type": action_type,
        "audit_id": audit.id,
        "actor": audit.actor,
        "created_at": audit.created_at,
    }
    for key, value in parameters.items():
        if isinstance(value, dict) and "id" in value:
            binds[key] = value["id"]
        elif isinstance(value, (str, int, float, bool)) or value is None:
            binds[key] = value
    return binds


def _human_action_line(action_type: str, parameters: dict[str, Any]) -> str:
    label = action_type.replace("_", " ")
    bits = [label]
    for key, value in parameters.items():
        if isinstance(value, dict) and value.get("id"):
            bits.append(f"{key} {value['id']}")
        elif isinstance(value, (str, int)) and value != "":
            bits.append(f"{key} {value}")
    return "Applied " + " · ".join(bits)
