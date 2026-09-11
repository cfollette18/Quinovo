"""Structured turn capture for the world pack.

Agents call ``save_turn`` at the end of every turn. The kernel also ingests
raw agent transcripts through the ``transcripts`` connector so a forgotten
tool call does not drop the conversation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from quinovo.entities import EntityIndex, clean_name, is_generic


def _about_names(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    names = [clean_name(item) for item in raw]
    return [name for name in names if name and not is_generic(name)][:6]


def _link_about_entities(
    kernel: Any,
    index: EntityIndex,
    link_type: str,
    from_id: str,
    names: list[str],
    topic_id: str,
    actor: str,
) -> None:
    try:
        kernel.ontology.link_type(link_type)
    except KeyError:
        return
    for name in names:
        entity_id = index.ensure(name, topic_id=topic_id, actor=actor)
        if entity_id is None:
            continue
        try:
            kernel.set_link(link_type, from_id, entity_id, actor=actor)
        except (KeyError, ValueError, PermissionError):
            continue


def link_fact_entities(
    kernel: Any,
    fact_id: str,
    subject: str,
    value: str,
    topic_id: str,
    actor: str,
    index: EntityIndex | None = None,
) -> None:
    """Attach a Fact to its subject Entity (created if new) and object Entity (if known)."""
    index = index or EntityIndex(kernel)
    if not index.enabled:
        return
    pairs: list[tuple[str, str | None]] = []
    if subject:
        pairs.append(("fact_subject", index.ensure(subject, topic_id=topic_id, actor=actor)))
    if value:
        pairs.append(("fact_object", index.resolve(value)))
    for link_type, entity_id in pairs:
        if entity_id is None:
            continue
        try:
            kernel.ontology.link_type(link_type)
            kernel.set_link(link_type, fact_id, entity_id, actor=actor)
        except (KeyError, ValueError, PermissionError):
            continue


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _slug(raw: str) -> str:
    text = raw.strip().lower().replace("_", "-")
    out: list[str] = []
    prev_dash = False
    for char in text:
        if char.isalnum():
            out.append(char)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def topic_path(raw: str) -> list[str]:
    """Split ``cretex/workflows`` into slug segments."""
    return [_slug(part) for part in raw.replace("\\", "/").split("/") if _slug(part)]


def _title(slug: str) -> str:
    known = {
        "cretex": "Cretex",
        "quinovo": "Quinovo",
        "workflows": "Workflows",
        "ivanti": "Ivanti",
        "epicor": "Epicor",
        "jira": "Jira",
        "faq-bot": "FAQ bot",
        "ticket-automation": "Ticket automation",
        "epicor-user-termination": "Epicor user termination",
        "documentation-automation": "Documentation automation",
        "mcp-servers": "MCP servers",
        "technology": "Technology",
    }
    if slug in known:
        return known[slug]
    return slug.replace("-", " ").title()


def ensure_topic(
    kernel: Any,
    topic: str,
    *,
    parent: str | None = None,
    description: str = "",
    actor: str = "mcp-agent",
) -> str:
    """Create a Topic (and optional parents) if missing. Never clobber existing ones."""
    segments = topic_path(topic)
    if not segments:
        raise ValueError("topic id is empty")
    chain = topic_path(parent) + segments if parent else segments
    previous: str | None = None
    for segment in chain:
        existing = kernel.store.get_object("Topic", segment)
        if existing is None:
            props: dict[str, Any] = {
                "id": segment,
                "name": _title(segment),
                "status": "active",
            }
            if description and segment == chain[-1]:
                props["description"] = description
            kernel.upsert_object("Topic", props, actor=actor)
        if previous is not None:
            kernel.set_link("subtopic_of", segment, previous, actor=actor)
        previous = segment
    return chain[-1]


def ensure_project(
    kernel: Any,
    project: str,
    topic: str,
    *,
    actor: str = "mcp-agent",
) -> str:
    project_id = _slug(project)
    if not project_id:
        raise ValueError("project id is empty")
    existing = kernel.store.get_object("Project", project_id)
    if existing is None:
        kernel.upsert_object(
            "Project",
            {
                "id": project_id,
                "name": _title(project_id),
                "status": "active",
                "recorded_at": datetime.now(UTC).isoformat(),
            },
            actor=actor,
        )
    kernel.set_link("project_in_topic", project_id, topic, actor=actor)
    return project_id


def save_turn(
    kernel: Any,
    session_id: str,
    turn_index: int,
    topic: str,
    summary: str,
    *,
    role: str = "",
    parent: str = "",
    project: str = "",
    facts: Any = None,
    decisions: Any = None,
    todos: Any = None,
    questions: Any = None,
    memories: Any = None,
    skills: Any = None,
    actor: str = "mcp-agent",
) -> dict[str, Any]:
    """Write one Conversation plus every structured claim, then nudge inference."""
    recorded_at = datetime.now(UTC).isoformat()
    conv_id = f"{session_id}:{turn_index}"
    topic_id = ensure_topic(kernel, topic, parent=parent or None, actor=actor)
    project_id = (
        ensure_project(kernel, project, topic_id, actor=actor) if project else ""
    )

    conv_props: dict[str, Any] = {
        "id": conv_id,
        "session_id": session_id,
        "turn_index": turn_index,
        "summary": summary,
        "recorded_at": recorded_at,
    }
    if role:
        conv_props["role"] = role
    kernel.upsert_object("Conversation", conv_props, actor=actor)
    kernel.set_link("conversation_in_topic", conv_id, topic_id, actor=actor)

    written: dict[str, list[str]] = {
        "facts": [],
        "decisions": [],
        "todos": [],
        "questions": [],
        "memories": [],
        "skills": [],
    }
    link_specs = {
        "fact": ("fact_in_topic", "produced", "facts", "Fact", "fact_under_project"),
        "decision": (
            "decision_in_topic",
            "decided",
            "decisions",
            "Decision",
            "decision_under_project",
        ),
        "todo": ("todo_in_topic", "spawned", "todos", "Todo", "todo_under_project"),
        "question": ("question_in_topic", "raised", "questions", "OpenQuestion", ""),
        "memory": ("memory_in_topic", "recorded", "memories", "Memory", ""),
        "skill": ("skill_in_topic", "authored", "skills", "Skill", ""),
    }
    type_props = {
        "fact": ("predicate", "value"),
        "decision": ("choice", "context"),
        "todo": ("text", "status"),
        "question": ("text", "status"),
        "memory": ("text", "kind"),
        "skill": ("name", "description"),
    }
    inputs = {
        "fact": _as_list(facts),
        "decision": _as_list(decisions),
        "todo": _as_list(todos),
        "question": _as_list(questions),
        "memory": _as_list(memories),
        "skill": _as_list(skills),
    }
    entity_links = {
        "todo": "todo_about_entity",
        "decision": "decision_about_entity",
        "question": "question_about_entity",
        "memory": "memory_about_entity",
    }
    index = EntityIndex(kernel)
    for kind, items in inputs.items():
        in_topic_link, conv_link, out_key, otype, project_link = link_specs[kind]
        primary, secondary = type_props[kind]
        for item in items:
            item = dict(item)
            about = _about_names(item.pop("about", None))
            if otype == "Fact" and "object" in item and "value" not in item:
                item["value"] = item.pop("object")
            elif "object" in item:
                item.pop("object")
            if "id" not in item or not item.get("id"):
                item["id"] = f"{kind}_{conv_id}_{len(written[out_key]) + 1}"
            item.setdefault("recorded_at", recorded_at)
            if otype in ("Fact", "Memory"):
                item.setdefault("confidence", 0.9)
            if otype == "Todo":
                item.setdefault("status", "open")
            if otype == "OpenQuestion":
                item.setdefault("status", "open")
            item.setdefault(primary, item.get(secondary, ""))
            kernel.upsert_object(otype, item, actor=actor)
            kernel.set_link(in_topic_link, item["id"], topic_id, actor=actor)
            kernel.set_link(conv_link, conv_id, item["id"], actor=actor)
            if project_id and project_link:
                kernel.set_link(project_link, item["id"], project_id, actor=actor)
            if otype == "Fact" and index.enabled:
                link_fact_entities(
                    kernel,
                    item["id"],
                    str(item.get("subject") or ""),
                    str(item.get("value") or ""),
                    topic_id,
                    actor,
                    index=index,
                )
            if about and index.enabled and kind in entity_links:
                _link_about_entities(
                    kernel, index, entity_links[kind], item["id"], about, topic_id, actor
                )
            written[out_key].append(item["id"])

    kernel.nudge()
    return {
        "conversation": conv_id,
        "topic": topic_id,
        "project": project_id or None,
        "recorded_at": recorded_at,
        "written": written,
    }
