"""Turn raw turns into Entities and Fact triples the graph can answer from.

Two entry points:

1. ``remember_text`` - one low-friction capture call. It writes the turn as a
   Conversation and extracts knowledge from it in the same call.
2. ``enrich_new_conversations`` - runs inside every ``tick``, so whatever lands
   in the index (``remember``, ``save_turn``, transcript ingest) grows entities
   and triples even when the agent never calls ``tick`` itself.

Extraction asks the configured language model for entities and triples and
resolves them against the Entities the world already has, so "Langfuse",
"langfuse", and "the Langfuse project" are one node. Without a model the
fallback only links mentions of Entities it already knows. It never invents a
Person from a capitalized word.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from quinovo.capture import ensure_topic
from quinovo.entities import EntityIndex, clean_name, is_generic, normalize_kind, slugify
from quinovo.llm.author import parse_json_object
from quinovo.llm.engine import LLMError, engine_from_settings
from quinovo.llm.settings import load_settings

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "v2"
MAX_CONVS_PER_TICK = 3
MAX_FACTS_PER_TEXT = 20
MAX_ENTITIES_PER_TEXT = 15
MAX_WORK_ITEMS = 6
MIN_FACT_CONFIDENCE = 0.5
DEFAULT_CONFIDENCE = 0.8
CLAIM_TTL = timedelta(minutes=10)
_TEXT_LIMIT = 6000
_SUMMARY_LIMIT = 4000
_KNOWN_ENTITIES_IN_PROMPT = 60
_PREDICATE_RE = re.compile(r"[^a-z0-9]+")
_WORK_ROLES = frozenset({"transcript", "observed"})


def _has_type(kernel: Any, api_name: str) -> bool:
    try:
        kernel.ontology.object_type(api_name)
        return True
    except KeyError:
        return False


def _has_link(kernel: Any, api_name: str) -> bool:
    try:
        kernel.ontology.link_type(api_name)
        return True
    except KeyError:
        return False


def _safe_link(kernel: Any, link_type: str, from_id: str, to_id: str, actor: str) -> bool:
    if not _has_link(kernel, link_type):
        return False
    try:
        kernel.set_link(link_type, from_id, to_id, actor=actor)
        return True
    except (KeyError, ValueError, PermissionError):
        return False


def _has_topic(kernel: Any, object_type: str, object_id: str) -> bool:
    try:
        return bool(kernel.store.search_around(object_type, object_id, "topic"))
    except KeyError:
        return False


def normalize_predicate(raw: Any) -> str:
    text = _PREDICATE_RE.sub("_", str(raw or "").strip().lower()).strip("_")
    return text[:40]


def fact_id_for(subject: str, predicate: str, value: str) -> str:
    key = f"{slugify(subject)}|{predicate}|{value.strip().lower()}"
    return "fact-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def memory_id_for(text: str) -> str:
    return "mem-" + hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:12]


# --- language-model extraction ----------------------------------------------


def _prompt(text: str, topic: str, known: list[str], include_work: bool) -> str:
    work = ""
    if include_work:
        work = (
            "Also list decisions that were made, todos that are still open, and "
            "questions left unanswered, each with the entity names it is about. "
            "Only include work that is clearly stated, never guessed.\n"
        )
    known_line = ", ".join(known) if known else "(none yet)"
    return (
        "You maintain a knowledge graph of a software engineer's work. Read the "
        "turn below and extract what a careful colleague would write on an index "
        "card: the specific things it is about and the claims it makes about them.\n"
        "Rules:\n"
        "- Entities are specific nouns: people, organizations, systems, tools, "
        "projects, places, concepts. Never 'the user', 'the assistant', 'the system', "
        "'the project', or other generic words. Reuse a known entity name when the "
        "text means the same thing.\n"
        "- Facts are triples: subject, predicate, object. The subject must be an "
        "entity. The object is an entity name when it names a thing, otherwise a "
        "short literal (a version, a port, a path, a date, a number, a short phrase). "
        "Predicates are short snake_case verbs: uses, runs_on, depends_on, owned_by, "
        "located_at, integrates_with, replaced_by, costs, listens_on, deployed_to, "
        "written_in, stores, blocked_on, decided, prefers.\n"
        "- Skip claims about the conversation itself (who asked what, what the "
        "assistant did). Keep claims about the world that stay true after the chat ends.\n"
        "- Durable preferences, habits, or lessons about how the engineer works go "
        "in memories, not facts.\n"
        f"{work}"
        "- Confidence is 0.5 to 1.0 and reflects how explicitly the text states it.\n"
        "Reply with JSON only, no prose:\n"
        '{"entities":[{"name":"Langfuse","kind":"tool","description":"one sentence"}],'
        '"facts":[{"subject":"Quinovo","predicate":"traces_with","object":"Langfuse",'
        '"confidence":0.9}],'
        '"memories":[{"text":"...","kind":"preference|environment|lesson|user",'
        '"about":["Entity"]}],'
        '"decisions":[{"choice":"...","context":"...","about":["Entity"]}],'
        '"todos":[{"text":"...","about":["Entity"]}],'
        '"questions":[{"text":"...","about":["Entity"]}]}\n'
        f"Kinds: person, organization, system, tool, project, place, concept.\n"
        f"Topic: {topic}\nKnown entities: {known_line}\n\nTurn:\n{text[:_TEXT_LIMIT]}"
    )


def _as_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _names(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        name = clean_name(item)
        if name and not is_generic(name):
            out.append(name)
    return out[:6]


def _clamp(raw: Any, default: float = DEFAULT_CONFIDENCE) -> float:
    try:
        return min(1.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return default


def parse_extraction(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Validate and trim a model reply into the shape ``write_extraction`` takes."""
    entities: list[dict[str, Any]] = []
    for row in _as_rows(raw.get("entities"))[:MAX_ENTITIES_PER_TEXT]:
        name = clean_name(row.get("name"))
        if not name or is_generic(name):
            continue
        entities.append(
            {
                "name": name,
                "kind": normalize_kind(row.get("kind")),
                "description": str(row.get("description") or "")[:280],
            }
        )
    facts: list[dict[str, Any]] = []
    for row in _as_rows(raw.get("facts"))[:MAX_FACTS_PER_TEXT]:
        subject = clean_name(row.get("subject"))
        predicate = normalize_predicate(row.get("predicate"))
        value = clean_name(row.get("object") if "object" in row else row.get("value"))
        if not subject or not predicate or not value or is_generic(subject):
            continue
        confidence = _clamp(row.get("confidence"))
        if confidence < MIN_FACT_CONFIDENCE:
            continue
        facts.append(
            {"subject": subject, "predicate": predicate, "value": value[:200], "confidence": confidence}
        )
    memories: list[dict[str, Any]] = []
    for row in _as_rows(raw.get("memories"))[:MAX_WORK_ITEMS]:
        text = str(row.get("text") or "").strip()
        if len(text) < 8:
            continue
        kind = str(row.get("kind") or "user").strip().lower()
        if kind not in {"user", "environment", "preference", "lesson"}:
            kind = "user"
        memories.append({"text": text[:400], "kind": kind, "about": _names(row.get("about"))})
    work: dict[str, list[dict[str, Any]]] = {"decisions": [], "todos": [], "questions": []}
    for row in _as_rows(raw.get("decisions"))[:MAX_WORK_ITEMS]:
        choice = str(row.get("choice") or row.get("text") or "").strip()
        if len(choice) < 8:
            continue
        work["decisions"].append(
            {
                "choice": choice[:400],
                "context": str(row.get("context") or "")[:400],
                "about": _names(row.get("about")),
            }
        )
    for key in ("todos", "questions"):
        for row in _as_rows(raw.get(key))[:MAX_WORK_ITEMS]:
            text = str(row.get("text") or "").strip()
            if len(text) < 8:
                continue
            work[key].append({"text": text[:400], "about": _names(row.get("about"))})
    return {"entities": entities, "facts": facts, "memories": memories, **work}


def llm_extract(
    text: str,
    *,
    topic: str,
    known: list[str],
    include_work: bool,
) -> dict[str, list[dict[str, Any]]] | None:
    """Ask the configured model for entities and triples. None when unconfigured or failed."""
    settings = load_settings()
    if not settings.ready():
        return None
    try:
        engine = engine_from_settings(settings)
        raw = engine.complete(
            _prompt(text, topic, known, include_work),
            max_tokens=2048,
            feature="extract-knowledge",
        )
        if engine.settings.api_key and engine.settings.api_key in raw:
            return None
        data = parse_json_object(raw)
    except (LLMError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("knowledge extraction failed: %s", exc)
        return None
    return parse_extraction(data)


# --- writing ------------------------------------------------------------------


def _write_fact(
    kernel: Any,
    index: EntityIndex,
    item: dict[str, Any],
    *,
    conv_id: str | None,
    topic_id: str,
    recorded_at: str,
    actor: str,
) -> str | None:
    subject_id = index.ensure(item["subject"], topic_id=topic_id, actor=actor)
    if subject_id is None:
        return None
    subject_obj = kernel.store.get_object("Entity", subject_id)
    subject_name = str((subject_obj.properties or {}).get("name") or item["subject"])
    predicate = item["predicate"]
    value = item["value"]
    object_id = index.resolve(value)
    if object_id is not None:
        object_obj = kernel.store.get_object("Entity", object_id)
        value = str((object_obj.properties or {}).get("name") or value)
    fact_id = fact_id_for(subject_name, predicate, value)
    existing = kernel.store.get_object("Fact", fact_id)
    confidence = float(item.get("confidence") or DEFAULT_CONFIDENCE)
    if existing is None:
        try:
            kernel.upsert_object(
                "Fact",
                {
                    "id": fact_id,
                    "subject": subject_name,
                    "predicate": predicate,
                    "value": value,
                    "confidence": confidence,
                    "recorded_at": recorded_at,
                },
                actor=actor,
            )
        except (KeyError, ValueError, PermissionError):
            return None
    else:
        previous = float((existing.properties or {}).get("confidence") or 0)
        if confidence > previous + 0.05:
            props = dict(existing.properties)
            props["confidence"] = confidence
            kernel.upsert_object("Fact", props, actor=actor)
    if existing is None or not _has_topic(kernel, "Fact", fact_id):
        # A fact lives in one topic: the topic of the turn that first said it.
        _safe_link(kernel, "fact_in_topic", fact_id, topic_id, actor)
    _safe_link(kernel, "fact_subject", fact_id, subject_id, actor)
    if object_id is not None:
        _safe_link(kernel, "fact_object", fact_id, object_id, actor)
        index.file_in_topic(object_id, topic_id, actor)
    if conv_id:
        _safe_link(kernel, "produced", conv_id, fact_id, actor)
    return fact_id if existing is None else None


def _link_about(
    kernel: Any,
    index: EntityIndex,
    link_type: str,
    from_id: str,
    names: list[str],
    topic_id: str,
    actor: str,
) -> None:
    for name in names:
        entity_id = index.ensure(name, topic_id=topic_id, actor=actor)
        if entity_id is not None:
            _safe_link(kernel, link_type, from_id, entity_id, actor)


def write_extraction(
    kernel: Any,
    extraction: dict[str, list[dict[str, Any]]],
    *,
    conv_id: str | None,
    topic_id: str,
    actor: str,
    index: EntityIndex | None = None,
) -> dict[str, list[str]]:
    """Write entities, triples, memories, and work items as linked objects."""
    written: dict[str, list[str]] = {
        "entities": [], "facts": [], "memories": [], "decisions": [], "todos": [], "questions": [],
    }
    index = index or EntityIndex(kernel)
    if not index.enabled:
        return written
    recorded_at = datetime.now(UTC).isoformat()
    for item in extraction.get("entities", []):
        before = set(index.by_id)
        entity_id = index.ensure(
            item["name"],
            kind=item.get("kind", "concept"),
            description=item.get("description", ""),
            topic_id=topic_id,
            actor=actor,
        )
        if entity_id and entity_id not in before:
            written["entities"].append(entity_id)
        if entity_id and conv_id:
            _safe_link(kernel, "mentions", conv_id, entity_id, actor)
    if _has_type(kernel, "Fact"):
        for item in extraction.get("facts", []):
            fact_id = _write_fact(
                kernel, index, item, conv_id=conv_id, topic_id=topic_id,
                recorded_at=recorded_at, actor=actor,
            )
            if fact_id:
                written["facts"].append(fact_id)
    if _has_type(kernel, "Memory"):
        for item in extraction.get("memories", []):
            mem_id = memory_id_for(item["text"])
            if kernel.store.get_object("Memory", mem_id) is None:
                try:
                    kernel.upsert_object(
                        "Memory",
                        {"id": mem_id, "text": item["text"], "kind": item["kind"],
                         "confidence": DEFAULT_CONFIDENCE, "recorded_at": recorded_at},
                        actor=actor,
                    )
                except (KeyError, ValueError, PermissionError):
                    continue
                written["memories"].append(mem_id)
            _safe_link(kernel, "memory_in_topic", mem_id, topic_id, actor)
            if conv_id:
                _safe_link(kernel, "recorded", conv_id, mem_id, actor)
            _link_about(kernel, index, "memory_about_entity", mem_id, item.get("about", []), topic_id, actor)
    stem = slugify(conv_id or recorded_at)[-32:]
    specs = (
        ("decisions", "Decision", "decision_in_topic", "decided", "decision_about_entity", "dec"),
        ("todos", "Todo", "todo_in_topic", "spawned", "todo_about_entity", "todo"),
        ("questions", "OpenQuestion", "question_in_topic", "raised", "question_about_entity", "q"),
    )
    for key, otype, in_topic, from_conv, about_link, prefix in specs:
        if not _has_type(kernel, otype):
            continue
        for n, item in enumerate(extraction.get(key, []), start=1):
            text = item.get("choice") or item.get("text") or ""
            digest = hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:8]
            item_id = f"{prefix}-{stem}-{digest}"
            if kernel.store.get_object(otype, item_id) is not None:
                continue
            props: dict[str, Any] = {"id": item_id, "recorded_at": recorded_at}
            if otype == "Decision":
                props["choice"] = item["choice"]
                props["context"] = item.get("context", "")
            else:
                props["text"] = item["text"]
                props["status"] = "open"
            try:
                kernel.upsert_object(otype, props, actor=actor)
            except (KeyError, ValueError, PermissionError):
                continue
            written[key].append(item_id)
            _safe_link(kernel, in_topic, item_id, topic_id, actor)
            if conv_id:
                _safe_link(kernel, from_conv, conv_id, item_id, actor)
            _link_about(kernel, index, about_link, item_id, item.get("about", []), topic_id, actor)
    return written


def link_mentions(
    kernel: Any,
    conv_id: str,
    text: str,
    topic_id: str,
    actor: str,
    index: EntityIndex | None = None,
) -> list[str]:
    """Fallback without a model: link the turn to Entities it names."""
    index = index or EntityIndex(kernel)
    found = index.mentions_in(text)
    for entity_id in found:
        _safe_link(kernel, "mentions", conv_id, entity_id, actor)
        index.file_in_topic(entity_id, topic_id, actor)
    return found


# --- per-conversation enrichment ------------------------------------------------


def _conversation_text(props: dict[str, Any]) -> str:
    return str(props.get("summary") or "").strip()


def _conversation_topic(kernel: Any, conv_id: str) -> str:
    try:
        neighbors = kernel.store.search_around("Conversation", conv_id, "topic")
    except KeyError:
        neighbors = []
    return neighbors[0].id if neighbors else "quinovo"


def _mark(kernel: Any, obj: Any, value: str) -> None:
    props = dict(obj.properties or {})
    props["enriched"] = value
    try:
        kernel.store.upsert_object("Conversation", props, source="action")
    except (KeyError, ValueError):
        return


def _claimed_recently(value: str) -> bool:
    if not value.startswith("claim@"):
        return False
    try:
        stamp = datetime.fromisoformat(value.split("@", 1)[1])
    except ValueError:
        return False
    return datetime.now(UTC) - stamp < CLAIM_TTL


def enrich_conversation(
    kernel: Any,
    obj: Any,
    actor: str,
    *,
    index: EntityIndex | None = None,
) -> dict[str, Any]:
    """Extract knowledge from one Conversation and stamp it as enriched."""
    props = obj.properties or {}
    text = _conversation_text(props)
    topic_id = _conversation_topic(kernel, obj.id)
    index = index or EntityIndex(kernel)
    result: dict[str, Any] = {"conversation": obj.id, "mode": "skipped", "written": {}}
    if len(text) < 12 or not index.enabled:
        _mark(kernel, obj, EXTRACTOR_VERSION)
        return result
    _mark(kernel, obj, f"claim@{datetime.now(UTC).isoformat()}")
    known = [name for name, _ in index.names()][:_KNOWN_ENTITIES_IN_PROMPT]
    include_work = str(props.get("role") or "") in _WORK_ROLES
    extraction = llm_extract(text, topic=topic_id, known=known, include_work=include_work)
    if extraction is None:
        mentioned = link_mentions(kernel, obj.id, text, topic_id, actor, index=index)
        result["mode"] = "mentions"
        result["written"] = {"entities": mentioned}
    else:
        result["mode"] = "llm"
        result["written"] = write_extraction(
            kernel, extraction, conv_id=obj.id, topic_id=topic_id, actor=actor, index=index
        )
    fresh = kernel.store.get_object("Conversation", obj.id)
    if fresh is not None:
        _mark(kernel, fresh, EXTRACTOR_VERSION)
    return result


def pending_conversations(kernel: Any) -> list[Any]:
    """Conversations the current extractor has not processed (or whose claim expired)."""
    if not _has_type(kernel, "Conversation"):
        return []
    found: list[Any] = []
    for obj in kernel.store.list_objects("Conversation"):
        stamp = str((obj.properties or {}).get("enriched") or "")
        if stamp == EXTRACTOR_VERSION or _claimed_recently(stamp):
            continue
        found.append(obj)
    found.sort(key=lambda item: str((item.properties or {}).get("recorded_at") or ""), reverse=True)
    return found


def enrich_new_conversations(
    kernel: Any,
    actor: str = "autonomous",
    *,
    limit: int = MAX_CONVS_PER_TICK,
) -> dict[str, Any]:
    """Enrich the newest Conversations the extractor has not seen yet.

    Called from ``tick`` (including the background loop). Each pass handles a
    few turns so a tick stays responsive; the backlog drains over time. A
    claim stamp keeps two processes on the same database from paying for the
    same model call.
    """
    result: dict[str, Any] = {
        "conversations": 0, "remaining": 0, "entities": [], "facts": [], "memories": [],
        "decisions": [], "todos": [], "questions": [], "mode": "skipped",
    }
    if not _has_type(kernel, "Conversation") or not _has_type(kernel, "Entity"):
        return result
    pending = pending_conversations(kernel)
    result["remaining"] = max(0, len(pending) - max(0, limit))
    if not pending:
        return result
    index = EntityIndex(kernel)
    for obj in pending[: max(0, limit)]:
        try:
            outcome = enrich_conversation(kernel, obj, actor, index=index)
        except Exception as exc:  # noqa: BLE001 - one bad turn must not break tick
            logger.warning("enrichment failed for %s: %s", obj.id, exc)
            continue
        result["conversations"] += 1
        if outcome["mode"] != "skipped":
            result["mode"] = outcome["mode"]
        for key, ids in (outcome.get("written") or {}).items():
            if key in result and isinstance(ids, list):
                result[key].extend(ids)
    return result


def remember_text(
    kernel: Any,
    text: str,
    *,
    topic: str = "quinovo",
    session_id: str = "autonomous",
    role: str = "observed",
    actor: str = "mcp-agent",
) -> dict[str, Any]:
    """Capture raw text as a Conversation and extract knowledge in the same call."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("text is empty")
    if not _has_type(kernel, "Conversation") or not _has_type(kernel, "Topic"):
        raise ValueError("this pack has no Conversation/Topic types")
    topic_id = ensure_topic(kernel, topic or "quinovo", actor=actor)
    recorded_at = datetime.now(UTC).isoformat()
    digest = hashlib.sha1(f"{session_id}|{recorded_at}|{cleaned}".encode()).hexdigest()[:10]
    conv_id = f"remember-{slugify(session_id)[-16:]}-{digest}"
    kernel.upsert_object(
        "Conversation",
        {"id": conv_id, "session_id": session_id, "turn_index": 0,
         "summary": cleaned[:_SUMMARY_LIMIT], "recorded_at": recorded_at, "role": role},
        actor=actor,
    )
    kernel.set_link("conversation_in_topic", conv_id, topic_id, actor=actor)
    obj = kernel.store.get_object("Conversation", conv_id)
    outcome = enrich_conversation(kernel, obj, actor) if obj is not None else {"mode": "skipped", "written": {}}
    kernel.nudge()
    return {
        "conversation": conv_id,
        "topic": topic_id,
        "recorded_at": recorded_at,
        "mode": outcome["mode"],
        "written": outcome["written"],
    }
