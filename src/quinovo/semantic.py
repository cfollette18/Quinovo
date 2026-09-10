"""Autonomous semantic enrichment: human-like connections from raw text.

The MCP server cannot force an arbitrary agent to call ``tick`` or
``save_turn`` — MCP is request/response, so a passive agent writes nothing.
Two changes close that gap:

1. ``remember_text`` — one low-friction capture call. It takes raw natural
   language, extracts the connections a human would see (who did what to
   whom, what contains what, what that implies), and writes them as linked
   Fact / Memory / Person objects. Agents call this instead of hand-structuring
   ``save_turn`` arguments.
2. ``enrich_new_conversations`` — runs inside every ``tick`` (including the
   background autonomy loop), so whatever lands in the index — via
   ``remember``, ``save_turn``, or transcript ingest — grows semantic
   connections even when the agent never calls ``tick`` itself.

Example: "Bob delivers a package that contains lipstick to Jerry" yields not
one fact but the human reading: Bob is the sender, Jerry the recipient, the
package contains lipstick, lipstick is a cosmetic (a plausible gift), Bob
knows Jerry, Jerry now has the lipstick, and the entities belong together.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

HEURISTIC_CONFIDENCE = 0.7
LLM_CONFIDENCE = 0.85
MAX_CLAIMS_PER_TEXT = 24
MAX_CONVS_PER_TICK = 10
_SUMMARY_LIMIT = 4000

_TRANSFER_VERBS = (
    "delivers?", "delivered", "delivering",
    "gives?", "gave", "given", "giving",
    "sends?", "sent", "sending",
    "hands?", "handed", "handing",
    "brings?", "brought", "bringing",
    "ships?", "shipped", "shipping",
    "carries", "carried", "carrying",
    "passes?", "passed", "passing",
    "offers?", "offered", "gifts?", "gifted",
)
_TRANSFER_RE = re.compile(r"\b(" + "|".join(_TRANSFER_VERBS) + r")\b", re.IGNORECASE)
_CONTAIN_RE = re.compile(
    r"\b(contains?|contained|containing|includes?|included|including|"
    r"holds?|held|holding|carries|carried|carrying|filled with|packed with)\b",
    re.IGNORECASE,
)
_RECIPIENT_RE = re.compile(
    r"\b(?:to|for)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
)
_SUBJECT_RE = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*$")
_NAME_RE = re.compile(r"\b([A-Z][a-z]{1,30}(?:\s+[A-Z][a-z]{1,30})?)\b")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?", re.DOTALL)
_WORD_RE = re.compile(r"[a-z][a-z0-9'-]*")

# Everyday nouns Quinovo types without a model call. Unknown nouns still get
# generic claims (sender/recipient/container); this table only adds the
# human-style "lipstick is a cosmetic / plausible gift" layer.
_CATEGORIES: dict[str, tuple[str, ...]] = {
    "lipstick": ("cosmetic", "gift", "personal item"),
    "perfume": ("cosmetic", "gift", "personal item"),
    "mascara": ("cosmetic", "personal item"),
    "ring": ("jewelry", "gift", "valuable"),
    "necklace": ("jewelry", "gift", "valuable"),
    "watch": ("accessory", "gift", "valuable"),
    "flowers": ("gift", "perishable"),
    "chocolate": ("food", "gift", "perishable"),
    "book": ("media", "gift"),
    "laptop": ("electronics", "valuable", "work tool"),
    "phone": ("electronics", "valuable", "personal item"),
    "keys": ("personal item", "access token"),
    "wallet": ("personal item", "valuable"),
    "bag": ("container", "personal item"),
    "box": ("container",),
    "package": ("container", "shipment"),
    "parcel": ("container", "shipment"),
    "envelope": ("container", "shipment"),
    "letter": ("document", "message"),
    "contract": ("document", "legal instrument"),
    "invoice": ("document", "financial record"),
}
_CONTAINER_WORDS = frozenset(
    {"package", "parcel", "box", "bag", "envelope", "crate", "bundle", "suitcase"}
)
_STOP_NAMES = frozenset(
    {"The", "This", "That", "These", "Those", "What", "When", "Where", "Which",
     "Who", "How", "There", "Here"}
)


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
    return "".join(out).strip("-") or "item"


def _verb_base(verb: str) -> str:
    return verb.lower().rstrip("s")


def _noun_key(phrase: str) -> str:
    words = _WORD_RE.findall(phrase.lower())
    stop = {"a", "an", "the", "that", "which", "with", "small", "large", "big",
            "new", "old", "red", "blue", "open", "closed"}
    content = [word for word in words if word not in stop]
    return " ".join(content) or phrase.strip().lower()


def _head_noun(phrase: str) -> str:
    words = _noun_key(phrase).split()
    return words[-1] if words else phrase.strip().lower()


def _names(text: str) -> list[str]:
    seen: list[str] = []
    for match in _NAME_RE.findall(text):
        first = match.split()[0]
        if first in _STOP_NAMES or match in seen:
            continue
        seen.append(match)
    return seen


def _claim(predicate: str, value: str, reason: str, confidence: float = HEURISTIC_CONFIDENCE) -> dict[str, Any]:
    return {
        "predicate": predicate,
        "value": value,
        "reason": reason,
        "confidence": confidence,
    }


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Heuristic semantic claims from raw text. No model, no I/O.

    Covers transfer events (Bob delivers X to Jerry), containment (a package
    containing lipstick), entity typing via a small lexicon, the social facts
    transfers imply (Bob knows Jerry; Jerry now has the lipstick), and
    co-mention grouping. Returns JSON-plain dicts with predicate/value/reason.
    """
    claims: list[dict[str, Any]] = []
    if not text or not text.strip():
        return claims
    for sentence in _SENTENCE_RE.findall(text):
        sentence = sentence.strip()
        if len(sentence) < 3:
            continue
        before = len(claims)
        claims.extend(_transfer_claims(sentence))
        claims.extend(_containment_claims(sentence))
        if len(claims) == before:
            claims.extend(_comention_claims(sentence))
        if len(claims) >= MAX_CLAIMS_PER_TEXT:
            break
    return claims[:MAX_CLAIMS_PER_TEXT]


def _transfer_claims(sentence: str) -> list[dict[str, Any]]:
    match = _TRANSFER_RE.search(sentence)
    if not match:
        return []
    verb = _verb_base(match.group(1))
    left = sentence[: match.start()]
    right = sentence[match.end():]
    subject = None
    subject_match = _SUBJECT_RE.search(left.strip())
    if subject_match and subject_match.group(1).split()[0] not in _STOP_NAMES:
        subject = subject_match.group(1)
    recipient_match = _RECIPIENT_RE.search(right)
    recipient = recipient_match.group(1) if recipient_match else None
    theme_raw = right
    if recipient_match:
        theme_raw = right[: recipient_match.start()]
    theme_raw = re.sub(r"\b(that|which|who|containing|contains|with|holding)\b.*$",
                       "", theme_raw, flags=re.IGNORECASE).strip()
    theme = _noun_key(theme_raw) or "item"
    if not subject and not recipient:
        return []
    actor = subject or "someone"
    claims = [
        _claim(
            "transfer",
            f"{actor} {verb} {theme}" + (f" to {recipient}" if recipient else ""),
            f"Transfer verb {verb!r} in: {sentence[:160]}",
        )
    ]
    if subject:
        claims.append(
            _claim("sender", subject,
                   f"{subject} is the giver in: {sentence[:160]}")
        )
    if recipient:
        claims.append(
            _claim("recipient", recipient,
                   f"{recipient} receives {theme} in: {sentence[:160]}")
        )
        claims.append(
            _claim("possesses", f"{recipient} has {theme}",
                   f"Receiving {theme} implies {recipient} now has it.")
        )
    if subject and recipient:
        claims.append(
            _claim("knows", f"{actor} knows {recipient}",
                   f"Handing {theme} over implies {actor} and {recipient} "
                   "have a connection.")
        )
    head = _head_noun(theme)
    for category in _CATEGORIES.get(head, ()):
        claims.append(
            _claim("is_a", f"{head} is a {category}",
                   f"{head!r} is commonly a {category}; "
                   f"carried inside {theme} here.")
        )
    if head in _CONTAINER_WORDS and recipient:
        claims.append(
            _claim("shipment", f"{theme} shipped to {recipient}",
                   f"{head!r} is a container addressed to {recipient}.")
        )
    return claims


def _containment_claims(sentence: str) -> list[dict[str, Any]]:
    match = _CONTAIN_RE.search(sentence)
    if not match:
        # "a package that contains lipstick" is caught above; this branch
        # handles bare "X with Y" only when X looks like a container.
        with_match = re.search(
            r"\b(package|parcel|box|bag|envelope|crate|bundle)\b(.{0,40}?)\bwith\b\s+(.+)$",
            sentence, flags=re.IGNORECASE)
        if not with_match:
            return []
        container = _noun_key(with_match.group(1) + with_match.group(2))
        content = _noun_key(with_match.group(3))
        return [
            _claim("contains", f"{container} contains {content}",
                   f"Container phrasing in: {sentence[:160]}")
        ]
    left = sentence[: match.start()]
    right = sentence[match.end():]
    container_match = re.search(
        r"((?:[A-Z][a-z]+\s+)?(?:package|parcel|box|bag|envelope|crate|bundle"
        r"|order|shipment|gift)|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
        r"|\bthe\s+[a-z][a-z0-9' -]{1,40})$",
        left.strip(), flags=re.IGNORECASE)
    container = _noun_key(container_match.group(1)) if container_match else ""
    content = _noun_key(re.split(r"\b(to|for|from)\b", right, flags=re.IGNORECASE)[0])
    if not container or not content:
        return []
    claims = [
        _claim("contains", f"{container} contains {content}",
               f"Containment in: {sentence[:160]}")
    ]
    head = _head_noun(content)
    for category in _CATEGORIES.get(head, ()):
        claims.append(
            _claim("is_a", f"{head} is a {category}",
                   f"{head!r} is commonly a {category}; found inside "
                   f"{container} here.")
        )
    if "gift" in _CATEGORIES.get(head, ()) and _RECIPIENT_RE.search(sentence):
        recipient = _RECIPIENT_RE.search(sentence).group(1)  # type: ignore[union-attr]
        claims.append(
            _claim("gift", f"{content} is a gift for {recipient}",
                   f"A {head} carried to {recipient} reads as a gift.")
        )
    return claims


def _comention_claims(sentence: str) -> list[dict[str, Any]]:
    names = _names(sentence)
    if len(names) < 2:
        return []
    return [
        _claim(
            "mentioned_with",
            f"{names[0]} mentioned with {', '.join(names[1:])}",
            f"Co-mentioned in one statement: {sentence[:160]}",
            confidence=0.6,
        )
    ]


def llm_claims(kernel: Any, text: str) -> list[dict[str, Any]]:
    """Ask the configured LLM for semantic triples. [] when unconfigured."""
    from quinovo.llm.engine import LLMError, engine_from_settings
    from quinovo.llm.settings import load_settings

    settings = load_settings()
    if not settings.ready():
        return []
    prompt = (
        "Extract the semantic connections a careful human would see in this "
        "text: who did what to whom, what contains what, what each thing is "
        "(lipstick is a cosmetic), what the event implies (the giver knows "
        "the recipient; the recipient now has the contents). Reply with JSON "
        "only, no prose:\n"
        '{"claims":[{"predicate":"transfer|sender|recipient|contains|is_a|'
        'knows|possesses|gift|shipment|mentioned_with","value":"short human '
        'sentence","confidence":0.85,"reason":"why, citing the text"}]}\n\n'
        f"Text:\n{text[:3000]}"
    )
    try:
        engine = engine_from_settings(settings)
        raw = engine.complete(prompt, max_tokens=1024, feature="semantic-claims")
        if engine.settings.api_key and engine.settings.api_key in raw:
            return []
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1])
    except (LLMError, json.JSONDecodeError, TypeError, ValueError):
        return []
    rows = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        predicate = str(row.get("predicate") or "").strip()
        value = str(row.get("value") or "").strip()
        if not predicate or not value:
            continue
        try:
            confidence = min(1.0, max(0.0, float(row.get("confidence") or 0)))
        except (TypeError, ValueError):
            continue
        if confidence <= 0:
            continue
        out.append({
            "predicate": predicate[:80],
            "value": value[:280],
            "reason": str(row.get("reason") or "")[:280],
            "confidence": confidence,
        })
    return out[:MAX_CLAIMS_PER_TEXT]


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


def _safe_link(kernel: Any, link_type: str, from_id: str, to_id: str, actor: str) -> None:
    if not _has_link(kernel, link_type):
        return
    try:
        kernel.set_link(link_type, from_id, to_id, actor=actor)
    except (KeyError, ValueError, PermissionError):
        return


def _existing_conv_facts(kernel: Any, conv_id: str) -> set[tuple[str, str]]:
    try:
        neighbors = kernel.store.search_around("Conversation", conv_id, "facts")
    except KeyError:
        return set()
    found: set[tuple[str, str]] = set()
    for item in neighbors:
        props = item.properties or {}
        found.add((str(props.get("predicate") or ""), str(props.get("value") or "")))
    return found


def _enrich_conversation(
    kernel: Any,
    conv_id: str,
    topic_id: str,
    text: str,
    actor: str,
) -> dict[str, list[str]]:
    """Extract claims for one conversation and write linked objects."""
    written: dict[str, list[str]] = {"facts": [], "memories": [], "persons": []}
    if not _has_type(kernel, "Fact"):
        return written
    try:
        claims = llm_claims(kernel, text)
    except Exception:  # noqa: BLE001 — enrichment must never break capture
        claims = []
    seen_keys = {(str(item.get("predicate") or "").lower(),
                  str(item.get("value") or "").lower()) for item in claims}
    for item in extract_claims(text):
        key = (item["predicate"].lower(), item["value"].lower())
        if key not in seen_keys:
            seen_keys.add(key)
            claims.append(item)
    if not claims:
        return written
    recorded_at = datetime.now(UTC).isoformat()
    existing = _existing_conv_facts(kernel, conv_id)
    can_person = _has_type(kernel, "Person")
    can_memory = _has_type(kernel, "Memory")
    for item in claims:
        predicate = item["predicate"][:80]
        value = item["value"][:280]
        if (predicate, value) in existing:
            continue
        digest = hashlib.sha1(
            f"{conv_id}|{predicate}|{value}".encode("utf-8")).hexdigest()[:10]
        fact_id = f"sem-{_slug(conv_id)[-24:]}-{digest}"
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence") or HEURISTIC_CONFIDENCE)))
        except (TypeError, ValueError):
            confidence = HEURISTIC_CONFIDENCE
        try:
            kernel.upsert_object(
                "Fact",
                {"id": fact_id, "predicate": predicate, "value": value,
                 "confidence": confidence, "recorded_at": recorded_at},
                actor=actor,
            )
        except (KeyError, ValueError, PermissionError):
            continue
        _safe_link(kernel, "fact_in_topic", fact_id, topic_id, actor)
        _safe_link(kernel, "produced", conv_id, fact_id, actor)
        written["facts"].append(fact_id)
        existing.add((predicate, value))
        if predicate in {"knows", "possesses", "gift", "transfer"} and can_memory:
            mem_id = f"mem-{digest}"
            try:
                kernel.upsert_object(
                    "Memory",
                    {"id": mem_id, "text": value, "kind": "user",
                     "confidence": confidence, "recorded_at": recorded_at},
                    actor=actor,
                )
            except (KeyError, ValueError, PermissionError):
                continue
            _safe_link(kernel, "memory_in_topic", mem_id, topic_id, actor)
            _safe_link(kernel, "recorded", conv_id, mem_id, actor)
            written["memories"].append(mem_id)
            if can_person:
                for name in _names(value):
                    person_id = _slug(name)
                    try:
                        kernel.upsert_object(
                            "Person", {"id": person_id, "name": name}, actor=actor)
                    except (KeyError, ValueError, PermissionError):
                        continue
                    _safe_link(kernel, "person_owns_memory", person_id, mem_id, actor)
                    if person_id not in written["persons"]:
                        written["persons"].append(person_id)
    return written


def remember_text(
    kernel: Any,
    text: str,
    *,
    topic: str = "quinovo",
    session_id: str = "autonomous",
    role: str = "observed",
    actor: str = "mcp-agent",
) -> dict[str, Any]:
    """Capture raw text as a Conversation and enrich it in the same call.

    This is the one-call path for agents that will never structure
    ``save_turn`` arguments: dump the turn text, get back linked Facts,
    Memories, and Persons plus the human-style connections between them.
    """
    from quinovo.capture import ensure_topic

    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("text is empty")
    if not _has_type(kernel, "Conversation") or not _has_type(kernel, "Topic"):
        raise ValueError("this pack has no Conversation/Topic types")
    topic_id = ensure_topic(kernel, topic or "quinovo", actor=actor)
    recorded_at = datetime.now(UTC).isoformat()
    digest = hashlib.sha1(
        f"{session_id}|{recorded_at}|{cleaned}".encode("utf-8")).hexdigest()[:10]
    conv_id = f"remember-{_slug(session_id)[-16:]}-{digest}"
    summary = cleaned[:_SUMMARY_LIMIT] or topic_id
    kernel.upsert_object(
        "Conversation",
        {"id": conv_id, "session_id": session_id, "turn_index": 0,
         "summary": summary, "recorded_at": recorded_at, "role": role},
        actor=actor,
    )
    kernel.set_link("conversation_in_topic", conv_id, topic_id, actor=actor)
    written = _enrich_conversation(kernel, conv_id, topic_id, cleaned, actor)
    kernel.nudge()
    return {
        "conversation": conv_id,
        "topic": topic_id,
        "recorded_at": recorded_at,
        "written": written,
    }


def enrich_new_conversations(
    kernel: Any,
    actor: str = "autonomous",
    *,
    limit: int = MAX_CONVS_PER_TICK,
) -> dict[str, Any]:
    """Enrich every Conversation the semantic pass has not seen yet.

    Called from ``tick`` (including the background loop), so knowledge grows
    even when the connected agent never calls ``tick`` or ``remember`` itself
    — e.g. turns that arrived via ``save_turn`` or transcript ingest.
    Idempotent: already-linked (predicate, value) pairs are skipped, so a
    restart re-scan writes nothing new.
    """
    result: dict[str, Any] = {
        "conversations": 0, "facts": [], "memories": [], "persons": [],
    }
    if not _has_type(kernel, "Conversation") or not _has_type(kernel, "Fact"):
        return result
    seen = getattr(kernel, "_semantic_seen", None)
    if not isinstance(seen, set):
        seen = set()
        kernel._semantic_seen = seen
    try:
        conversations = kernel.store.list_objects("Conversation")
    except (KeyError, ValueError):
        return result
    pending = [item for item in conversations if item.id not in seen]
    for obj in pending[: max(0, limit)]:
        seen.add(obj.id)
        props = obj.properties or {}
        text = str(props.get("summary") or "")
        if len(text.strip()) < 3:
            continue
        topic_id = "quinovo"
        try:
            neighbors = kernel.store.search_around(
                "Conversation", obj.id, "topic")
            if neighbors:
                topic_id = neighbors[0].id
        except KeyError:
            pass
        try:
            written = _enrich_conversation(kernel, obj.id, topic_id, text, actor)
        except Exception:  # noqa: BLE001 — one bad turn must not break tick
            continue
        if written["facts"] or written["memories"]:
            result["conversations"] += 1
            result["facts"].extend(written["facts"])
            result["memories"].extend(written["memories"])
            result["persons"].extend(written["persons"])
    return result
