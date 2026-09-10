"""Plain-language labels for workspace pages. JSON stays behind a toggle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def words(api_name: str) -> str:
    text = str(api_name or "").replace("-", "_")
    return " ".join(part for part in text.split("_") if part)


def title_case(api_name: str) -> str:
    return words(api_name).title()


def sentence_case(api_name: str) -> str:
    text = words(api_name)
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def object_name(payload: dict[str, Any]) -> str:
    props = payload.get("properties") or {}
    for key in ("name", "title", "label", "display_name"):
        value = props.get(key)
        if value:
            return str(value)
    return str(payload.get("id") or payload.get("pk") or "")


def confidence_label(value: object) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if number <= 1:
        number *= 100
    return f"{int(round(number))}% sure"


def status_label(status: str) -> str:
    match status:
        case "pending":
            return "Needs a look"
        case "asserted" | "active" | "ok":
            return "Confirmed"
        case "applied":
            return "Done"
        case "rejected":
            return "Turned down"
        case "":
            return ""
        case _ as other:
            return title_case(other)


def kind_label(kind: str) -> str:
    mapping = {
        "type_definition": "New kind of thing",
        "inference_rule": "A pattern Quinovo noticed",
        "classification": "A guess about what this is",
        "link_type": "A new kind of connection",
        "action_type": "A new action",
        "action_application": "A suggested action",
        "pack": "A workspace change",
    }
    return mapping.get(kind, title_case(kind))


def _parameters_phrase(parameters: object) -> str:
    if isinstance(parameters, dict):
        parts: list[str] = []
        for key, value in parameters.items():
            if isinstance(value, dict) and value.get("id"):
                parts.append(f"{words(str(key))} {value['id']}")
            elif value is None or value == "":
                continue
            else:
                parts.append(f"{words(str(key))} {value}")
        return ", ".join(parts)
    if isinstance(parameters, list):
        names: list[str] = []
        for item in parameters:
            if not isinstance(item, dict):
                continue
            name = item.get("api_name") or item.get("name")
            if name:
                names.append(words(str(name)))
        return ", ".join(names)
    return ""


def _type_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(title_case(str(item)) for item in value if item)
    if value:
        return title_case(str(value))
    return "objects"


def _classification_why(payload: dict[str, Any]) -> str:
    object_type = title_case(str(payload.get("object_type") or "object"))
    props = payload.get("properties")
    if isinstance(props, list):
        bits: list[str] = []
        for item in props:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("api_name")
            if not name:
                continue
            label = title_case(str(name))
            typ = item.get("type")
            if typ:
                label = f"{label} ({typ})"
            desc = str(item.get("description") or "").strip()
            bits.append(f"{label}: {desc}" if desc else label)
        if bits:
            joined = "; ".join(bits)
            return f"Live {object_type} objects look like they need {joined}"
    if isinstance(props, dict):
        keys = ", ".join(title_case(str(key)) for key in props if key not in {"id", "pk"})
        pk = props.get("id") or props.get("pk")
        if pk and keys:
            return f"Quinovo guessed {object_type} {pk} from {keys}."
        if pk:
            return f"Quinovo guessed this is {object_type} {pk}."
        if keys:
            return f"Quinovo guessed this is a {object_type} because of {keys}."
    return f"Quinovo guessed this is a {object_type}."


def proposal_title(kind: str, payload: dict[str, Any] | None) -> str:
    data = payload or {}
    match kind:
        case "action_application":
            return title_case(str(data.get("action_type") or "action"))
        case "classification":
            props = data.get("properties")
            if isinstance(props, list):
                for item in props:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("api_name")
                        if name:
                            obj = title_case(str(data.get("object_type") or ""))
                            field = title_case(str(name))
                            return f"{obj} · {field}".strip(" ·")
            if isinstance(props, dict) and (props.get("id") or props.get("pk")):
                return f"{title_case(str(data.get('object_type') or 'object'))} {props.get('id') or props.get('pk')}"
            return title_case(str(data.get("object_type") or "classification"))
        case "action_type" | "link_type" | "inference_rule" | "type_definition" | "pack":
            return title_case(str(data.get("api_name") or data.get("name") or kind))
        case "":
            return "Proposal"
        case _ as other:
            return title_case(str(data.get("api_name") or data.get("name") or other))


def proposal_why(kind: str, payload: dict[str, Any] | None) -> str:
    """Evidence for the human: why this was proposed now, not the spec text."""
    data = payload or {}
    reason = str(data.get("reason") or "").strip()
    if reason:
        return reason
    match kind:
        case "action_application":
            action = title_case(str(data.get("action_type") or "this action"))
            target = _parameters_phrase(data.get("parameters"))
            if target:
                return f"Apply {action} to {target}."
            return f"Apply {action}."
        case "action_type":
            name = title_case(str(data.get("api_name") or "this action"))
            needed = _parameters_phrase(data.get("parameters"))
            if needed:
                return f"The pack has no {name} action yet. It would take {needed}."
            return f"The pack has no {name} action yet."
        case "link_type":
            name = title_case(str(data.get("api_name") or "this link"))
            origin = _type_list(data.get("from_types") or data.get("from_type"))
            dest = _type_list(data.get("to_types") or data.get("to_type"))
            return f"The pack has no {name} connection from {origin} to {dest}."
        case "classification":
            return _classification_why(data)
        case "inference_rule" | "type_definition" | "pack":
            desc = str(data.get("description") or "").strip()
            if desc:
                return desc
            name = title_case(str(data.get("api_name") or data.get("name") or kind))
            return f"Quinovo proposed {name} from the live index."
        case "":
            return "Quinovo did not say why."
        case _ as other:
            desc = str(data.get("description") or "").strip()
            if desc:
                return desc
            return f"Quinovo proposed {title_case(other)} from the live index."


def proposal_what(kind: str, payload: dict[str, Any] | None) -> str:
    """Spec text (what it is) when that is distinct from why now."""
    data = payload or {}
    desc = str(data.get("description") or "").strip()
    if not desc:
        return ""
    if desc == proposal_why(kind, data):
        return ""
    return desc


def proposal_target(kind: str, payload: dict[str, Any] | None) -> str:
    data = payload or {}
    match kind:
        case "action_application":
            phrase = _parameters_phrase(data.get("parameters"))
            return f"On {phrase}." if phrase else ""
        case _:
            return ""


def family_label(family: str) -> str:
    match family:
        case "things":
            return "Thing"
        case "connections":
            return "Connection"
        case "noticed":
            return "What Quinovo noticed"
        case "changed":
            return "What changed"
        case _ as other:
            return title_case(other)


def size_class_label(size: str) -> str:
    match size:
        case "tiny":
            return "Tiny specialist"
        case "small":
            return "Small specialist"
        case "medium":
            return "Medium specialist"
        case _ as other:
            return title_case(other)


def fact_line(predicate: object, value: object) -> str:
    """One human sentence. Never `predicate=value` or Type:id."""
    pred = sentence_case(str(predicate or ""))
    raw = "" if value is None else str(value).strip()
    low = raw.lower()
    if low in {"true", "1", "yes"}:
        return pred or "Something Quinovo noticed"
    if low in {"false", "0", "no", ""}:
        base = words(str(predicate or ""))
        return f"Not {base}".strip() if base else "Not the case"
    pretty = title_case(raw) if ("_" in raw or "-" in raw) else raw
    key = words(str(predicate or "")).lower()
    if key in {"recommended action", "suggested action"}:
        return f"Suggested: {pretty}"
    if pred:
        return f"{pred} — {pretty}"
    return pretty


def mask_secret(value: object) -> str:
    """Show only the last four characters of a secret. Never the full value."""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "••••"
    return f"••••{text[-4:]}"


def relative_time(iso: object, *, now: datetime | None = None) -> str:
    """A short human phrase: just now, 2 minutes ago, yesterday."""
    text = str(iso or "").strip()
    if not text:
        return ""
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    delta = current - stamp.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 45:
        return "just now"
    if seconds < 90:
        return "a minute ago"
    if seconds < 3600:
        return f"{seconds // 60} minutes ago"
    if seconds < 5400:
        return "an hour ago"
    if seconds < 86400:
        return f"{seconds // 3600} hours ago"
    days = seconds // 86400
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    return stamp.date().isoformat()


def thing_count(count: object) -> str:
    try:
        number = int(count)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "things"
    if number == 1:
        return "1 thing"
    return f"{number} things"


def connection_kind_label(kind: str) -> str:
    mapping = {
        "http": "Web address",
        "json": "JSON feed",
        "csv": "Spreadsheet",
        "webhook": "Incoming push",
        "sql": "Database",
        "mcp": "MCP",
        "transcripts": "Agent transcripts",
        "synthetic": "Demo data",
        "callable": "Custom",
        "email": "Email",
        "slack": "Slack",
    }
    return mapping.get(kind, title_case(kind))


def source_status_line(item: dict[str, Any]) -> str:
    if not item.get("enabled", True):
        return "Paused"
    kind = item.get("kind") or ""
    last = item.get("last_run") or {}
    if not last:
        if kind == "webhook":
            return "Waiting for another system to send things in"
        return "Not pulled yet"
    when = relative_time(last.get("created_at"))
    if last.get("status") == "error":
        return f"Last pull failed · {when}" if when else "Last pull failed"
    count = thing_count(last.get("upserted") or 0)
    if when:
        return f"Last pulled {count} · {when}"
    return f"Last pulled {count}"


def target_status_line(item: dict[str, Any]) -> str:
    raw = str(item.get("kind") or "")
    kind = "Webhook" if raw in {"webhook", "http"} else connection_kind_label(raw)
    if not item.get("enabled", True):
        return f"Write-back to {kind} · paused"
    last = item.get("last_dispatch") or {}
    if not last:
        return f"Write-back to {kind} · not sent yet"
    when = relative_time(last.get("created_at"))
    result = last.get("result")
    if result == "failed":
        return f"Write-back to {kind} · last send failed" + (f" · {when}" if when else "")
    if when:
        return f"Write-back to {kind} · last sent {when}"
    return f"Write-back to {kind}"


def catalog_kind_name(api_name: str) -> str:
    mapping = {
        "Topic": "Topic",
        "Conversation": "Conversation",
        "Fact": "Fact",
        "Memory": "Memory",
        "Todo": "To-do",
        "Decision": "Decision",
        "OpenQuestion": "Open question",
        "Skill": "Skill",
        "Person": "Person",
        "Project": "Project",
        "Package": "Package",
    }
    return mapping.get(api_name, title_case(api_name))


def catalog_kind_blurb(api_name: str, description: str = "") -> str:
    mapping = {
        "Topic": "A basket of similar things. Subtopics nest inside, the way tropical fruit sits inside fruit.",
        "Conversation": "One chat or turn, kept with the topic it belongs to.",
        "Fact": "One thing we know, written so it can be found later.",
        "Memory": "Something to remember across chats.",
        "Todo": "Work that still needs doing.",
        "Decision": "A choice that was made, and why.",
        "OpenQuestion": "A question that is still open.",
        "Skill": "A saved way of doing something.",
        "Person": "Someone named in this workspace.",
        "Project": "A named effort inside a topic.",
    }
    return mapping.get(api_name) or (description.strip() or f"A kind of {catalog_kind_name(api_name).lower()}.")


def catalog_action_blurb(description: str) -> str:
    text = (description or "").strip()
    if text:
        return text
    return "An action Quinovo can run after you approve it."


def actor_label(actor: object) -> str:
    text = str(actor or "").strip()
    if not text or text in {"autonomous", "mcp-agent", "quinovo-ai"}:
        return "Quinovo"
    if text in {"human", "local"}:
        return "You"
    return title_case(text)
