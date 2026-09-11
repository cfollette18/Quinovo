"""Ask the ontology questions in plain language: recall, about, briefing.

Three reads an agent needs at the start of a session and before it answers:

- briefing(): what is live right now, in a page - active topics, open and
  stale work, recent decisions and memories, the most-connected entities,
  and what is waiting on a human.
- about(name): everything the graph knows about one Entity or Topic, as
  sentences, walking both directions of every typed link.
- recall(query): ranked text search across every object type, scoped to a
  topic when asked, each hit rendered as one human line.

Everything here is read-only, bounded, and written for a language model to
consume: short lines, stable keys, no raw property dumps.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from quinovo.apps.humanize import sentence_case
from quinovo.entities import EntityIndex, slugify
from quinovo.topics import catalog_topics, has_topic_type, topic_descendants

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-\.]{1,}")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "do",
        "does",
        "did",
        "not",
        "no",
        "yes",
        "into",
        "over",
        "under",
        "about",
        "after",
        "before",
        "than",
        "then",
        "so",
        "if",
    ]
)
TEXT_PROPERTIES = (
    "name",
    "title",
    "summary",
    "text",
    "choice",
    "context",
    "reasoning",
    "subject",
    "predicate",
    "value",
    "description",
    "aliases",
    "question",
    "quote",
    "statement",
    "control",
    "kind",
    "status",
)
OPEN_STATUSES = frozenset({"open", "captured", "pending", "in_progress", ""})
MAX_LIMIT = 100
SNIPPET_CHARS = 200
SUMMARY_CHARS = 280


def _clamp(limit: int) -> int:
    return max(1, min(int(limit or 1), MAX_LIMIT))


def _tokens(text: str) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(text.lower()) if tok not in STOPWORDS]


def _clip(text: str, chars: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= chars:
        return text
    return text[: chars - 1].rstrip() + "…"


def _props(obj: Any) -> dict[str, Any]:
    return obj.properties or {}


def _title_of(kernel: Any, obj: Any) -> str:
    try:
        prop = kernel.ontology.object_type(obj.object_type).title_property
    except KeyError:
        prop = "name"
    props = _props(obj)
    return str(props.get(prop) or props.get("name") or obj.id)


def _searchable_text(obj: Any) -> str:
    props = _props(obj)
    bits = [obj.id.replace("-", " ").replace("_", " ")]
    for key in TEXT_PROPERTIES:
        value = props.get(key)
        if value:
            bits.append(str(value))
    return " ".join(bits)


def _recorded_at(obj: Any) -> str:
    return str(_props(obj).get("recorded_at") or "")


def _is_open(obj: Any) -> bool:
    return str(_props(obj).get("status") or "").lower() in OPEN_STATUSES


def fact_sentence(subject: str, predicate: str, value: str) -> str:
    """'Langfuse runs on Docker' rather than predicate=value."""
    pred = " ".join(str(predicate or "").replace("_", " ").split())
    subj = str(subject or "").strip()
    val = str(value or "").strip()
    if subj and pred and val:
        return f"{subj} {pred} {val}"
    if pred and val:
        return f"{sentence_case(pred)}: {val}"
    return sentence_case(pred) or val or subj


def describe(kernel: Any, obj: Any) -> str:
    """One human line per object, whatever its type."""
    props = _props(obj)
    match obj.object_type:
        case "Fact":
            return fact_sentence(
                str(props.get("subject") or ""),
                str(props.get("predicate") or ""),
                str(props.get("value") or ""),
            )
        case "Todo":
            status = str(props.get("status") or "open")
            return f"Todo ({status}): {props.get('text') or obj.id}"
        case "OpenQuestion":
            status = str(props.get("status") or "open")
            return f"Question ({status}): {props.get('text') or obj.id}"
        case "Decision":
            line = f"Decided: {props.get('choice') or obj.id}"
            context = str(props.get("context") or "").strip()
            if context and context != str(props.get("choice") or ""):
                line += f" — because {context}"
            return line
        case "Memory":
            kind = str(props.get("kind") or "").strip()
            prefix = f"Memory ({kind})" if kind else "Memory"
            return f"{prefix}: {props.get('text') or obj.id}"
        case "Conversation":
            return f"Turn: {_clip(str(props.get('summary') or obj.id), SUMMARY_CHARS)}"
        case "Entity":
            kind = str(props.get("kind") or "").strip()
            desc = str(props.get("description") or "").strip()
            line = f"{props.get('name') or obj.id}"
            if kind:
                line += f" ({kind})"
            if desc:
                line += f": {desc}"
            return line
        case "Topic":
            desc = str(props.get("description") or "").strip()
            name = str(props.get("name") or obj.id)
            return f"Topic {name}: {desc}" if desc else f"Topic {name}"
        case "Skill":
            desc = str(props.get("description") or "").strip()
            return (
                f"Skill {props.get('name') or obj.id}: {desc}"
                if desc
                else f"Skill {props.get('name') or obj.id}"
            )
        case _:
            title = _title_of(kernel, obj)
            desc = str(props.get("description") or props.get("summary") or "").strip()
            base = f"{sentence_case(obj.object_type)} {title}"
            return f"{base}: {_clip(desc, SNIPPET_CHARS)}" if desc else base


class _Graph:
    """One pass over the link table so about()/briefing() never query per node."""

    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel
        self.out: dict[tuple[str, str], list[Any]] = defaultdict(list)
        self.inc: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for link in kernel.store.list_all_links():
            self.out[(link.from_type, link.from_id)].append(link)
            self.inc[(link.to_type, link.to_id)].append(link)
        self._cache: dict[tuple[str, str], Any] = {}

    def get(self, object_type: str, id: str) -> Any:
        key = (object_type, id)
        if key not in self._cache:
            self._cache[key] = self.kernel.store.get_object(object_type, id)
        return self._cache[key]

    def neighbors(self, object_type: str, id: str, link_type: str, *, outgoing: bool) -> list[Any]:
        table = self.out if outgoing else self.inc
        found: list[Any] = []
        for link in table.get((object_type, id), []):
            if link.link_type != link_type:
                continue
            other = (
                self.get(link.to_type, link.to_id)
                if outgoing
                else self.get(link.from_type, link.from_id)
            )
            if other is not None:
                found.append(other)
        return found

    def topic_of(self, obj: Any) -> str:
        for link in self.out.get((obj.object_type, obj.id), []):
            if link.to_type == "Topic" and link.link_type.endswith("_in_topic"):
                return link.to_id
        return ""

    def degree(self, object_type: str, id: str) -> int:
        key = (object_type, id)
        return len(self.out.get(key, [])) + len(self.inc.get(key, []))


def _hit(kernel: Any, graph: _Graph, obj: Any, score: float = 0.0) -> dict[str, Any]:
    payload = {
        "type": obj.object_type,
        "id": obj.id,
        "line": describe(kernel, obj),
        "topic": graph.topic_of(obj),
        "recorded_at": _recorded_at(obj),
    }
    if score:
        payload["score"] = round(score, 3)
    return payload


def _by_recency(objects: list[Any]) -> list[Any]:
    return sorted(objects, key=_recorded_at, reverse=True)


def recall(
    kernel: Any,
    query: str,
    *,
    topic: str | None = None,
    types: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Ranked text search across the ontology. Each hit is one human line."""
    limit = _clamp(limit)
    query = str(query or "").strip()
    q_tokens = _tokens(query)
    q_lower = query.lower()
    if not q_tokens and not q_lower:
        return {"query": query, "hits": [], "total": 0}

    scope: set[str] | None = None
    if topic and has_topic_type(kernel):
        topic_id = slugify(topic.split("/")[-1])
        scope = topic_descendants(kernel, topic_id) | {topic_id}

    wanted = {str(t) for t in types} if types else None
    graph = _Graph(kernel)
    scored: list[tuple[float, Any]] = []
    for type_def in kernel.ontology.object_types:
        if wanted and type_def.api_name not in wanted:
            continue
        for obj in kernel.store.list_objects(type_def.api_name):
            if (
                scope is not None
                and obj.object_type != "Topic"
                and graph.topic_of(obj) not in scope
            ):
                continue
            if scope is not None and obj.object_type == "Topic" and obj.id not in scope:
                continue
            text = _searchable_text(obj)
            low = text.lower()
            title = _title_of(kernel, obj).lower()
            score = 0.0
            if q_lower and q_lower in low:
                score += 3.0
            if q_lower and q_lower in title:
                score += 3.0
            text_tokens = set(_tokens(low))
            hits = sum(1 for tok in q_tokens if tok in text_tokens)
            if hits:
                score += 2.0 * hits / max(1, len(q_tokens))
            if not score:
                continue
            if obj.object_type in {"Entity", "Fact", "Decision", "Memory"}:
                score += 0.5
            score += min(graph.degree(obj.object_type, obj.id), 20) / 40.0
            scored.append((score, obj))
    scored.sort(key=lambda item: _recorded_at(item[1]), reverse=True)
    scored.sort(key=lambda item: item[0], reverse=True)
    top = [_hit(kernel, graph, obj, score) for score, obj in scored[:limit]]
    return {"query": query, "topic": topic or None, "hits": top, "total": len(scored)}


def _entity_view(kernel: Any, graph: _Graph, entity: Any, limit: int) -> dict[str, Any]:
    props = _props(entity)
    name = str(props.get("name") or entity.id)
    facts_about = graph.neighbors("Entity", entity.id, "fact_subject", outgoing=False)
    facts_mentioning = graph.neighbors("Entity", entity.id, "fact_object", outgoing=False)
    related: dict[str, int] = defaultdict(int)
    for fact in facts_about:
        for other in graph.neighbors("Fact", fact.id, "fact_object", outgoing=True):
            if other.id != entity.id:
                related[other.id] += 1
    for fact in facts_mentioning:
        for other in graph.neighbors("Fact", fact.id, "fact_subject", outgoing=True):
            if other.id != entity.id:
                related[other.id] += 1
    related_lines = []
    for other_id, weight in sorted(related.items(), key=lambda item: -item[1])[:limit]:
        other = graph.get("Entity", other_id)
        if other is not None:
            related_lines.append(
                {"id": other.id, "line": describe(kernel, other), "shared_facts": weight}
            )

    def about_items(link_type: str) -> list[dict[str, Any]]:
        items = graph.neighbors("Entity", entity.id, link_type, outgoing=False)
        return [_hit(kernel, graph, item) for item in _by_recency(items)[:limit]]

    conversations = graph.neighbors("Entity", entity.id, "mentions", outgoing=False)
    topics = graph.neighbors("Entity", entity.id, "entity_in_topic", outgoing=True)
    return {
        "kind": "entity",
        "id": entity.id,
        "name": name,
        "line": describe(kernel, entity),
        "aliases": [a for a in str(props.get("aliases") or "").split(" | ") if a],
        "topics": [t.id for t in topics],
        "facts": [describe(kernel, f) for f in _by_recency(facts_about)[:limit]],
        "mentioned_in_facts": [describe(kernel, f) for f in _by_recency(facts_mentioning)[:limit]],
        "related_entities": related_lines,
        "todos": about_items("todo_about_entity"),
        "decisions": about_items("decision_about_entity"),
        "open_questions": about_items("question_about_entity"),
        "memories": about_items("memory_about_entity"),
        "conversations": [_hit(kernel, graph, c) for c in _by_recency(conversations)[:limit]],
        "counts": {
            "facts": len(facts_about),
            "mentioned_in_facts": len(facts_mentioning),
            "conversations": len(conversations),
        },
    }


def _topic_side(kernel: Any, graph: _Graph, topic_id: str, from_type: str) -> list[Any]:
    link_type = ""
    for spec in kernel.ontology.link_types:
        if spec.from_type == from_type and spec.to_type == "Topic":
            link_type = spec.api_name
            break
    if not link_type:
        return []
    return graph.neighbors("Topic", topic_id, link_type, outgoing=False)


def _topic_view(kernel: Any, graph: _Graph, topic: Any, limit: int) -> dict[str, Any]:
    props = _props(topic)
    todos = _topic_side(kernel, graph, topic.id, "Todo")
    questions = _topic_side(kernel, graph, topic.id, "OpenQuestion")
    decisions = _topic_side(kernel, graph, topic.id, "Decision")
    memories = _topic_side(kernel, graph, topic.id, "Memory")
    facts = _topic_side(kernel, graph, topic.id, "Fact")
    conversations = _topic_side(kernel, graph, topic.id, "Conversation")
    entities = _topic_side(kernel, graph, topic.id, "Entity")
    entities.sort(key=lambda e: -graph.degree("Entity", e.id))
    children = graph.neighbors("Topic", topic.id, "subtopic_of", outgoing=False)
    parents = graph.neighbors("Topic", topic.id, "subtopic_of", outgoing=True)
    return {
        "kind": "topic",
        "id": topic.id,
        "name": str(props.get("name") or topic.id),
        "line": describe(kernel, topic),
        "status": str(props.get("status") or "active"),
        "parent": parents[0].id if parents else "",
        "subtopics": [c.id for c in children],
        "entities": [describe(kernel, e) for e in entities[:limit]],
        "open_todos": [
            _hit(kernel, graph, t) for t in _by_recency([t for t in todos if _is_open(t)])[:limit]
        ],
        "open_questions": [
            _hit(kernel, graph, q)
            for q in _by_recency([q for q in questions if _is_open(q)])[:limit]
        ],
        "decisions": [_hit(kernel, graph, d) for d in _by_recency(decisions)[:limit]],
        "memories": [_hit(kernel, graph, m) for m in _by_recency(memories)[:limit]],
        "facts": [describe(kernel, f) for f in _by_recency(facts)[:limit]],
        "conversations": [_hit(kernel, graph, c) for c in _by_recency(conversations)[:limit]],
        "counts": {
            "conversations": len(conversations),
            "facts": len(facts),
            "entities": len(entities),
            "todos": len(todos),
            "open_todos": sum(1 for t in todos if _is_open(t)),
            "open_questions": sum(1 for q in questions if _is_open(q)),
            "decisions": len(decisions),
            "memories": len(memories),
        },
    }


def about(kernel: Any, name: str, *, limit: int = 20) -> dict[str, Any]:
    """Everything the graph knows about one Entity or Topic, as sentences."""
    limit = _clamp(limit)
    name = str(name or "").strip()
    if not name:
        return {"kind": "none", "name": name, "suggestions": []}
    graph = _Graph(kernel)
    index = EntityIndex(kernel)
    entity_id = index.resolve(name) if index.enabled else None
    if entity_id:
        entity = graph.get("Entity", entity_id)
        if entity is not None:
            return _entity_view(kernel, graph, entity, limit)
    if has_topic_type(kernel):
        topic = graph.get("Topic", slugify(name.split("/")[-1]))
        if topic is not None:
            return _topic_view(kernel, graph, topic, limit)
    fallback = recall(kernel, name, limit=min(limit, 10))
    return {
        "kind": "none",
        "name": name,
        "line": f"Nothing is filed under {name!r} yet.",
        "suggestions": fallback["hits"],
    }


def _flatten_topics(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for node in nodes:
        flat.append(node)
        flat.extend(_flatten_topics(node.get("children") or []))
    return flat


def _stale_ids(kernel: Any, object_type: str) -> set[str]:
    found: set[str] = set()
    for fact in kernel.store.list_inferred_facts(object_type, None, status="asserted"):
        if fact.predicate == "stale" and str(fact.value).lower() in {"true", "1", "yes"}:
            found.add(fact.object_id)
    return found


def _open_items(kernel: Any, graph: _Graph, object_type: str, limit: int) -> list[dict[str, Any]]:
    if not any(t.api_name == object_type for t in kernel.ontology.object_types):
        return []
    stale = _stale_ids(kernel, object_type)
    items = [o for o in kernel.store.list_objects(object_type) if _is_open(o)]
    ordered = _by_recency([o for o in items if o.id in stale]) + _by_recency(
        [o for o in items if o.id not in stale]
    )
    out = []
    for obj in ordered[:limit]:
        hit = _hit(kernel, graph, obj)
        hit["stale"] = obj.id in stale
        out.append(hit)
    return out


def _recent(kernel: Any, graph: _Graph, object_type: str, limit: int) -> list[dict[str, Any]]:
    if not any(t.api_name == object_type for t in kernel.ontology.object_types):
        return []
    return [
        _hit(kernel, graph, o) for o in _by_recency(kernel.store.list_objects(object_type))[:limit]
    ]


def briefing(kernel: Any, *, limit: int = 10) -> dict[str, Any]:
    """What is live right now, in one page an agent can read at session start."""
    limit = _clamp(limit)
    graph = _Graph(kernel)
    topics: list[dict[str, Any]] = []
    if has_topic_type(kernel):
        flat = _flatten_topics(catalog_topics(kernel))
        flat = [
            t
            for t in flat
            if t.get("status") != "archived" and (t.get("counts") or {}).get("items", 0) > 0
        ]
        flat.sort(key=lambda t: -((t.get("counts") or {}).get("items", 0)))
        topics = [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t.get("description") or "",
                "parent": t.get("parent_id") or "",
                "items": (t.get("counts") or {}).get("items", 0),
            }
            for t in flat[:limit]
        ]

    entities: list[dict[str, Any]] = []
    if any(t.api_name == "Entity" for t in kernel.ontology.object_types):
        ranked = sorted(
            kernel.store.list_objects("Entity"),
            key=lambda e: -graph.degree("Entity", e.id),
        )
        entities = [
            {"id": e.id, "line": describe(kernel, e), "links": graph.degree("Entity", e.id)}
            for e in ranked[:limit]
            if graph.degree("Entity", e.id) > 0
        ]

    conversations = (
        _by_recency(kernel.store.list_objects("Conversation"))
        if any(t.api_name == "Conversation" for t in kernel.ontology.object_types)
        else []
    )
    hitl = {
        "proposals": len(kernel.store.list_proposals("pending")),
        "inferred_facts": len(kernel.store.list_inferred_facts(None, None, status="pending")),
        "actions": len(kernel.store.list_pending_actions("pending")),
    }
    return {
        "pack": kernel.ontology.ontology.api_name,
        "topics": topics,
        "open_todos": _open_items(kernel, graph, "Todo", limit),
        "open_questions": _open_items(kernel, graph, "OpenQuestion", limit),
        "recent_decisions": _recent(kernel, graph, "Decision", limit),
        "memories": _recent(kernel, graph, "Memory", limit),
        "entities": entities,
        "recent_conversations": [_hit(kernel, graph, c) for c in conversations[: min(limit, 5)]],
        "last_turn_at": _recorded_at(conversations[0]) if conversations else "",
        "waiting_on_human": hitl,
        "counts": {
            t.api_name: len(kernel.store.list_objects(t.api_name))
            for t in kernel.ontology.object_types
        },
    }
