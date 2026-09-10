"""Topics are baskets of similar objects, nested as subtopics.

The loop creates missing baskets on its own: known parent/child hints,
prefix nesting for orphans, and clusters of similar unfiled objects.
An optional language-model pass can propose extra baskets when configured.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from quinovo.capture import _title, ensure_topic, topic_path
from quinovo.llm.engine import LLMError, engine_from_settings
from quinovo.llm.settings import load_settings

MIN_CLUSTER = 3
MAX_NEW_PER_PASS = 20
TOKEN_RE = re.compile(r"[a-z][a-z0-9]{3,}")
STOPWORDS = frozenset(
    ["about", "across", "action", "actions", "actual", "actually", "adding", "after", "again", "along", "already", "alright", "also", "another", "around", "asked", "available", "back", "been", "before", "better", "briefly", "building", "built", "call", "called", "change", "chat", "code", "copy", "create", "current", "currently", "data", "description", "doing", "down", "each", "edit", "every", "example", "exist", "explain", "file", "files", "find", "first", "flow", "follow", "found", "full", "fully", "here", "high", "home", "include", "instead", "into", "itself", "just", "keep", "know", "label", "like", "likely", "line", "list", "live", "local", "look", "looks", "loop", "made", "main", "making", "more", "most", "move", "must", "name", "named", "names", "need", "needed", "needs", "never", "nothing", "only", "over", "page", "plus", "rather", "read", "ready", "real", "return", "right", "same", "serve", "show", "similar", "simple", "some", "something", "source", "start", "state", "still", "such", "summary", "system", "systems", "than", "that", "them", "then", "there", "these", "they", "thing", "things", "this", "those", "through", "title", "under", "unless", "update", "using", "view", "want", "well", "were", "what", "when", "which", "while", "will", "with", "within", "work", "working", "would", "could", "should", "write", "your", "from", "have", "here", "into", "object", "objects", "topic", "topics", "item", "items", "user", "users", "test", "tests", "todo", "todos", "fact", "facts", "mentions", "quinovo", "cursor", "agent", "agents", "session", "turn", "turns", "true", "false", "none", "null", "status", "active", "open", "based", "notes", "talk", "talked"]
)
PROTECTED_TOPICS = frozenset(
    {
        "quinovo",
        "cretex",
        "technology",
        "workflows",
        "mcp-servers",
        "ivanti",
        "epicor",
        "jira",
        "ticket-automation",
        "epicor-user-termination",
        "documentation-automation",
        "faq-bot",
        "jig",
        "orzo",
    }
)

# Baskets we already know belong together. Created only when the parent exists
# and live evidence (or an existing child) supports the grouping.
KNOWN_BASKETS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "cretex",
        "mcp-servers",
        "MCP servers",
        "Connectors and MCP servers built for Cretex.",
        ("mcp", "model context protocol"),
    ),
    (
        "cretex",
        "technology",
        "Technology",
        "Cretex systems and platforms: Ivanti, Epicor, Jira, and related tooling.",
        ("ivanti", "epicor", "jira"),
    ),
    (
        "cretex",
        "workflows",
        "Workflows",
        "Planned Cretex IT automations: ticket routing, user termination, docs, FAQ bot.",
        ("workflow", "automation", "ticket"),
    ),
)

CONTENT_SIDES = (
    "contents",
    "facts",
    "memories",
    "todos",
    "decisions",
    "open_questions",
    "skills",
    "projects",
)

SIDE_LABELS = {
    "contents": "conversations",
    "facts": "facts",
    "memories": "memories",
    "todos": "to-dos",
    "decisions": "decisions",
    "open_questions": "open questions",
    "skills": "skills",
    "projects": "projects",
}


def has_topic_type(kernel: Any) -> bool:
    return any(item.api_name == "Topic" for item in kernel.ontology.object_types)


def in_topic_links(kernel: Any) -> dict[str, str]:
    """from_type -> link api_name for every 'this object lives in a Topic' verb."""
    found: dict[str, str] = {}
    for spec in kernel.ontology.link_types:
        if spec.to_type == "Topic" and spec.from_type != "Topic":
            found[spec.from_type] = spec.api_name
    return found


def topic_parent(kernel: Any, topic_id: str) -> str | None:
    try:
        neighbors = kernel.store.search_around("Topic", topic_id, "parent")
    except KeyError:
        return None
    return neighbors[0].id if neighbors else None


def topic_children(kernel: Any, topic_id: str) -> list[str]:
    try:
        neighbors = kernel.store.search_around("Topic", topic_id, "subtopics")
    except KeyError:
        return []
    return [item.id for item in neighbors]


def _object_text(obj: Any) -> str:
    props = obj.properties or {}
    bits: list[str] = []
    for key in ("name", "title", "summary", "text", "description", "value", "choice"):
        value = props.get(key)
        if value:
            bits.append(str(value))
    return " ".join(bits).lower()


def _tokens(text: str) -> set[str]:
    found: set[str] = set()
    for match in TOKEN_RE.findall(text.lower()):
        if match in STOPWORDS:
            continue
        found.add(match)
    return found


def _side_count(kernel: Any, topic_id: str, side: str) -> int:
    try:
        return len(kernel.store.search_around("Topic", topic_id, side))
    except KeyError:
        return 0


def topic_counts(kernel: Any, topic_id: str) -> dict[str, int]:
    counts = {SIDE_LABELS[side]: _side_count(kernel, topic_id, side) for side in CONTENT_SIDES}
    counts["subtopics"] = _side_count(kernel, topic_id, "subtopics")
    counts["items"] = sum(counts[SIDE_LABELS[side]] for side in CONTENT_SIDES)
    return counts


def _topic_node(kernel: Any, obj: Any, children_map: dict[str, list[str]], by_id: dict[str, Any]) -> dict[str, Any]:
    props = obj.properties or {}
    child_ids = sorted(children_map.get(obj.id, []))
    return {
        "id": obj.id,
        "name": str(props.get("name") or _title(obj.id)),
        "description": str(props.get("description") or ""),
        "status": str(props.get("status") or "active"),
        "counts": topic_counts(kernel, obj.id),
        "children": [
            _topic_node(kernel, by_id[child_id], children_map, by_id)
            for child_id in child_ids
            if child_id in by_id
        ],
    }


def catalog_topics(kernel: Any) -> list[dict[str, Any]]:
    """Forest of Topic baskets, roots first, children nested."""
    if not has_topic_type(kernel):
        return []
    objects = kernel.store.list_objects("Topic")
    by_id = {obj.id: obj for obj in objects}
    children_map: dict[str, list[str]] = defaultdict(list)
    parents: dict[str, str] = {}
    for obj in objects:
        parent_id = topic_parent(kernel, obj.id)
        if parent_id and parent_id in by_id:
            parents[obj.id] = parent_id
            children_map[parent_id].append(obj.id)
    roots = [obj for obj in objects if obj.id not in parents]
    roots.sort(key=lambda item: str((item.properties or {}).get("name") or item.id).lower())
    return [_topic_node(kernel, obj, children_map, by_id) for obj in roots]


def _existing_ids(kernel: Any) -> set[str]:
    if not has_topic_type(kernel):
        return set()
    return {obj.id for obj in kernel.store.list_objects("Topic")}


def _link_subtopic(kernel: Any, child_id: str, parent_id: str, actor: str) -> None:
    if child_id == parent_id:
        return
    current = topic_parent(kernel, child_id)
    if current == parent_id:
        return
    if current is not None:
        return
    kernel.set_link("subtopic_of", child_id, parent_id, actor=actor)


def _evidence_text(kernel: Any) -> str:
    bits: list[str] = []
    if not has_topic_type(kernel):
        return ""
    for obj in kernel.store.list_objects("Topic"):
        bits.append(_object_text(obj))
    for type_name in in_topic_links(kernel):
        for obj in kernel.store.list_objects(type_name)[:80]:
            bits.append(_object_text(obj))
    return " ".join(bits)


def _ensure_known_baskets(kernel: Any, actor: str, created: list[str]) -> None:
    ids = _existing_ids(kernel)
    haystack = _evidence_text(kernel)
    for parent_id, child_id, name, description, needles in KNOWN_BASKETS:
        if parent_id not in ids:
            continue
        if child_id in ids:
            _link_subtopic(kernel, child_id, parent_id, actor)
            continue
        evidenced = any(needle in haystack for needle in needles)
        if not evidenced and parent_id != "cretex":
            continue
        if len(created) >= MAX_NEW_PER_PASS:
            return
        was_new = kernel.store.get_object("Topic", child_id) is None
        ensure_topic(
            kernel,
            child_id,
            parent=parent_id,
            description=description,
            actor=actor,
        )
        obj = kernel.store.get_object("Topic", child_id)
        if obj is not None:
            props = dict(obj.properties)
            props["name"] = name
            if description and not props.get("description"):
                props["description"] = description
            kernel.upsert_object("Topic", props, actor=actor)
        if was_new:
            created.append(child_id)
        ids.add(child_id)


def _best_parent(topic_id: str, ids: set[str]) -> str | None:
    parts = topic_id.split("-")
    if len(parts) < 2:
        return None
    for end in range(len(parts) - 1, 0, -1):
        candidate = "-".join(parts[:end])
        if candidate in ids and candidate != topic_id:
            return candidate
    for start in range(1, len(parts)):
        candidate = "-".join(parts[start:])
        if candidate in ids and candidate != topic_id:
            return candidate
    return None


def _nest_orphan_prefixes(kernel: Any, actor: str) -> None:
    ids = _existing_ids(kernel)
    for topic_id in sorted(ids, key=len, reverse=True):
        if topic_parent(kernel, topic_id):
            continue
        parent_id = _best_parent(topic_id, ids)
        if parent_id:
            _link_subtopic(kernel, topic_id, parent_id, actor)


def _unfiled_objects(kernel: Any) -> list[Any]:
    found: list[Any] = []
    links = in_topic_links(kernel)
    for type_name, link_name in links.items():
        spec = kernel.ontology.link_type(link_name)
        for obj in kernel.store.list_objects(type_name):
            try:
                neighbors = kernel.store.search_around(type_name, obj.id, spec.from_name)
            except KeyError:
                neighbors = []
            if not neighbors:
                found.append(obj)
    return found


def _file_in_topic(kernel: Any, obj: Any, topic_id: str, actor: str) -> None:
    link_name = in_topic_links(kernel).get(obj.object_type)
    if not link_name:
        return
    spec = kernel.ontology.link_type(link_name)
    try:
        existing = kernel.store.search_around(obj.object_type, obj.id, spec.from_name)
    except KeyError:
        existing = []
    if existing:
        return
    kernel.set_link(link_name, obj.id, topic_id, actor=actor)


def _cluster_unfiled(kernel: Any, actor: str, created: list[str]) -> None:
    unfiled = _unfiled_objects(kernel)
    buckets: dict[str, list[Any]] = defaultdict(list)
    for obj in unfiled:
        for token in _tokens(_object_text(obj)):
            buckets[token].append(obj)
    for token, members in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(created) >= MAX_NEW_PER_PASS:
            return
        unique: dict[tuple[str, str], Any] = {}
        for obj in members:
            unique[(obj.object_type, obj.id)] = obj
        group = list(unique.values())
        if len(group) < MIN_CLUSTER:
            continue
        topic_id = topic_path(token)[0] if topic_path(token) else ""
        if not topic_id or topic_id in STOPWORDS:
            continue
        if kernel.store.get_object("Topic", topic_id) is None:
            ensure_topic(
                kernel,
                topic_id,
                description=f"Similar things Quinovo grouped around {_title(topic_id)}.",
                actor=actor,
            )
            created.append(topic_id)
        for obj in group:
            _file_in_topic(kernel, obj, topic_id, actor)


def prune_empty_leaves(kernel: Any, actor: str) -> list[str]:
    """Remove empty non-protected topics left by over-eager grouping."""
    pruned: list[str] = []
    if not has_topic_type(kernel):
        return pruned
    for _ in range(8):
        removed = 0
        for obj in list(kernel.store.list_objects("Topic")):
            if obj.id in PROTECTED_TOPICS:
                continue
            counts = topic_counts(kernel, obj.id)
            if counts["items"] or counts["subtopics"]:
                continue
            if obj.id not in STOPWORDS and "-" in obj.id:
                continue
            try:
                kernel.delete_object("Topic", obj.id, actor=actor)
            except KeyError:
                continue
            pruned.append(obj.id)
            removed += 1
        if not removed:
            break
    return pruned


def _llm_baskets(kernel: Any, actor: str, created: list[str]) -> None:
    settings = load_settings()
    if not settings.ready() or len(created) >= MAX_NEW_PER_PASS:
        return
    snapshot = {
        "topics": [
            {
                "id": obj.id,
                "name": (obj.properties or {}).get("name"),
                "description": (obj.properties or {}).get("description"),
                "parent": topic_parent(kernel, obj.id),
            }
            for obj in kernel.store.list_objects("Topic")[:80]
        ],
        "unfiled": [
            {"type": obj.object_type, "id": obj.id, "text": _object_text(obj)[:240]}
            for obj in _unfiled_objects(kernel)[:40]
        ],
        "samples": [
            {"type": obj.object_type, "id": obj.id, "text": _object_text(obj)[:240]}
            for type_name in list(in_topic_links(kernel))[:6]
            for obj in kernel.store.list_objects(type_name)[:8]
        ],
    }
    prompt = (
        "You group similar objects into Topics. A Topic is a basket of similar "
        "things. Subtopics nest (fruit → tropical fruit → orange tropical fruit). "
        "Cretex may have subtopics such as technology, workflows, and MCP servers.\n"
        "Propose only named subject areas (employers, products, systems, projects). "
        "Never propose a topic whose id is a common English word "
        "(actually, across, this, those, building, looking). "
        "Propose only new Topic baskets that are not already listed. "
        "Confidence below 0.8 is ignored. Reply with JSON only:\n"
        '{"topics":[{"id":"slug","name":"Name","parent":"parent-slug-or-empty",'
        '"description":"one sentence","confidence":0.9,"reason":"why now"}]}\n\n'
        f"Live index:\n{json.dumps(snapshot, default=str)}"
    )
    try:
        engine = engine_from_settings(settings)
        text = engine.complete(prompt, max_tokens=1024, feature="propose-topics")
        if engine.settings.api_key and engine.settings.api_key in text:
            return
        blob = text.strip()
        start = blob.find("{")
        end = blob.rfind("}")
        if start < 0 or end <= start:
            return
        raw = json.loads(blob[start : end + 1])
    except (LLMError, json.JSONDecodeError, TypeError, ValueError):
        return
    rows = raw.get("topics") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return
    for row in rows:
        if len(created) >= MAX_NEW_PER_PASS:
            return
        if not isinstance(row, dict):
            continue
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if confidence < 0.8:
            continue
        slug_parts = topic_path(str(row.get("id") or row.get("name") or ""))
        if not slug_parts:
            continue
        topic_id = slug_parts[-1]
        if topic_id in STOPWORDS or topic_id in PROTECTED_TOPICS:
            continue
        parent_raw = str(row.get("parent") or "").strip()
        parent_id = topic_path(parent_raw)[-1] if parent_raw and topic_path(parent_raw) else None
        if kernel.store.get_object("Topic", topic_id) is not None:
            if parent_id:
                _link_subtopic(kernel, topic_id, parent_id, actor)
            continue
        ensure_topic(
            kernel,
            topic_id,
            parent=parent_id,
            description=str(row.get("description") or ""),
            actor=actor,
        )
        created.append(topic_id)


def organize_topics(
    kernel: Any,
    actor: str = "autonomous",
    *,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Create missing Topic baskets and nest orphans. Idempotent."""
    created: list[str] = []
    if not has_topic_type(kernel):
        return {"created": created, "pruned": [], "topics": []}
    before = _existing_ids(kernel)
    _ensure_known_baskets(kernel, actor, created)
    _nest_orphan_prefixes(kernel, actor)
    _cluster_unfiled(kernel, actor, created)
    if use_llm:
        _llm_baskets(kernel, actor, created)
    pruned = prune_empty_leaves(kernel, actor)
    after = _existing_ids(kernel)
    created = [item for item in created if item in after]
    extra = sorted(after - before - set(created))
    created.extend(extra)
    return {
        "created": created[:MAX_NEW_PER_PASS],
        "pruned": pruned,
        "topics": catalog_topics(kernel),
    }
