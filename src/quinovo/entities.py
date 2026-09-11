"""Entity resolution for the world pack: one row per thing, however it is spelled.

An Entity is a noun the world keeps talking about. This module owns the slug
rules, the alias lookup, and the "ensure it exists" write so every extractor,
capture path, and recall query agrees on which row "Langfuse" is.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

ENTITY_KINDS: tuple[str, ...] = (
    "person",
    "organization",
    "system",
    "tool",
    "project",
    "place",
    "concept",
)
ALIAS_SEP = " | "
MAX_NAME = 80

# Words that never name a specific thing on their own. A model that returns
# these as entities is describing the conversation, not the world.
GENERIC_NAMES = frozenset(
    {
        "user", "the user", "users", "assistant", "the assistant", "agent", "the agent",
        "agents", "system", "the system", "team", "people", "someone", "anyone",
        "everyone", "we", "i", "you", "it", "they", "me", "us", "them", "this", "that",
        "these", "those", "project", "the project", "tool", "tools", "model", "models",
        "file", "files", "code", "repo", "repository", "server", "servers", "service",
        "database", "data", "config", "configuration", "session", "conversation",
        "turn", "task", "tasks", "work", "issue", "issues", "bug", "bugs", "error",
        "errors", "feature", "features", "plan", "step", "steps", "phase", "stage",
        "test", "tests", "example", "examples", "key", "keys", "secret", "secrets",
        "token", "tokens", "api", "api key", "public key", "secret key", "video",
        "topic", "topics", "fact", "facts", "memory", "memories", "todo", "todos",
        "after", "before", "if", "in", "no", "not", "yes", "an", "a", "the", "every",
        "four", "software", "hardware", "staff", "service account", "chat", "protected",
    }
)
# "the Langfuse project" and "our Epicor instance" mean Langfuse and Epicor.
TRAILING_QUALIFIERS = frozenset(
    {"project", "tool", "system", "server", "service", "instance", "platform", "app",
     "application", "repo", "repository", "database", "db", "api", "sdk", "cli", "ui"}
)
LEADING_QUALIFIERS = frozenset({"my", "our", "your", "their", "local", "new", "old"})
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def slugify(raw: str) -> str:
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


def clean_name(raw: Any) -> str:
    """Trim, drop a leading article, collapse whitespace, cap length."""
    text = _WS_RE.sub(" ", str(raw or "")).strip().strip("\"'`.,;:")
    text = _ARTICLE_RE.sub("", text).strip()
    return text[:MAX_NAME]


def is_generic(name: str) -> bool:
    key = name.strip().lower()
    if not key or key in GENERIC_NAMES:
        return True
    if len(key) < 2:
        return True
    # A bare pronoun-ish or stop-word slug is never an entity.
    return slugify(key) in {"", "-"} or slugify(key) in GENERIC_NAMES


def normalize_kind(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in ENTITY_KINDS:
        return key
    aliases = {
        "human": "person", "people": "person", "user": "person", "engineer": "person",
        "company": "organization", "org": "organization", "employer": "organization",
        "vendor": "organization", "team": "organization",
        "software": "tool", "library": "tool", "framework": "tool", "product": "tool",
        "app": "tool", "application": "tool", "language": "tool", "sdk": "tool",
        "service": "system", "platform": "system", "database": "system", "server": "system",
        "host": "system", "machine": "system", "device": "system", "infrastructure": "system",
        "initiative": "project", "workflow": "project", "repo": "project",
        "repository": "project", "codebase": "project",
        "location": "place", "city": "place", "site": "place",
        "idea": "concept", "topic": "concept", "pattern": "concept", "principle": "concept",
        "process": "concept", "technique": "concept", "term": "concept",
    }
    return aliases.get(key, "concept")


def split_aliases(raw: Any) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in str(raw).split("|") if part.strip()]


class EntityIndex:
    """In-memory lookup over the pack's Entities. Cheap to build; rebuild per pass."""

    def __init__(self, kernel: Any) -> None:
        self.kernel = kernel
        self.enabled = _has_type(kernel, "Entity")
        self.by_id: dict[str, Any] = {}
        self.by_key: dict[str, str] = {}
        if self.enabled:
            for obj in kernel.store.list_objects("Entity"):
                self._index(obj)

    def _index(self, obj: Any) -> None:
        props = obj.properties or {}
        self.by_id[obj.id] = obj
        self.by_key[obj.id] = obj.id
        name = str(props.get("name") or "")
        if name:
            self.by_key[name.lower()] = obj.id
            self.by_key[slugify(name)] = obj.id
        for alias in split_aliases(props.get("aliases")):
            self.by_key[alias.lower()] = obj.id
            self.by_key[slugify(alias)] = obj.id

    def names(self) -> list[tuple[str, str]]:
        """(display name, id) for every entity, longest names first for matching."""
        pairs: list[tuple[str, str]] = []
        for obj in self.by_id.values():
            props = obj.properties or {}
            name = str(props.get("name") or obj.id)
            pairs.append((name, obj.id))
            for alias in split_aliases(props.get("aliases")):
                pairs.append((alias, obj.id))
        pairs.sort(key=lambda pair: -len(pair[0]))
        return pairs

    def resolve(self, name: str) -> str | None:
        if not self.enabled:
            return None
        cleaned = clean_name(name)
        if not cleaned:
            return None
        candidates = [cleaned]
        words = cleaned.split()
        if len(words) > 1 and words[-1].lower() in TRAILING_QUALIFIERS:
            candidates.append(" ".join(words[:-1]))
        if len(words) > 1 and words[0].lower() in LEADING_QUALIFIERS:
            candidates.append(" ".join(words[1:]))
        for candidate in candidates:
            for key in (candidate.lower(), slugify(candidate)):
                found = self.by_key.get(key)
                if found:
                    return found
        return None

    def ensure(
        self,
        name: str,
        *,
        kind: str = "concept",
        description: str = "",
        topic_id: str | None = None,
        actor: str = "autonomous",
    ) -> str | None:
        """Return the id for this name, creating the Entity when it is new.

        Generic words never become entities. When the name resolves to an
        existing row, a new spelling is added to its aliases.
        """
        if not self.enabled:
            return None
        cleaned = clean_name(name)
        if not cleaned or is_generic(cleaned):
            return None
        existing_id = self.resolve(cleaned)
        if existing_id is not None:
            self._learn_alias(existing_id, cleaned, description, actor)
            if topic_id:
                self.file_in_topic(existing_id, topic_id, actor)
            return existing_id
        entity_id = slugify(cleaned)
        if not entity_id or entity_id in GENERIC_NAMES:
            return None
        props: dict[str, Any] = {
            "id": entity_id,
            "name": cleaned,
            "kind": normalize_kind(kind),
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        if description:
            props["description"] = str(description)[:280]
        try:
            self.kernel.upsert_object("Entity", props, actor=actor)
        except (KeyError, ValueError, PermissionError):
            return None
        obj = self.kernel.store.get_object("Entity", entity_id)
        if obj is None:
            return None
        self._index(obj)
        if topic_id:
            self.file_in_topic(entity_id, topic_id, actor)
        return entity_id

    def _learn_alias(self, entity_id: str, spelling: str, description: str, actor: str) -> None:
        obj = self.by_id.get(entity_id)
        if obj is None:
            return
        props = dict(obj.properties or {})
        name = str(props.get("name") or "")
        aliases = split_aliases(props.get("aliases"))
        known = {name.lower(), *(alias.lower() for alias in aliases)}
        changed = False
        if spelling.lower() not in known and len(aliases) < 12:
            aliases.append(spelling)
            props["aliases"] = ALIAS_SEP.join(aliases)
            changed = True
        if description and not props.get("description"):
            props["description"] = str(description)[:280]
            changed = True
        if not changed:
            return
        try:
            self.kernel.upsert_object("Entity", props, actor=actor)
        except (KeyError, ValueError, PermissionError):
            return
        refreshed = self.kernel.store.get_object("Entity", entity_id)
        if refreshed is not None:
            self._index(refreshed)

    def file_in_topic(self, entity_id: str, topic_id: str, actor: str) -> None:
        if not _has_link(self.kernel, "entity_in_topic"):
            return
        try:
            self.kernel.set_link("entity_in_topic", entity_id, topic_id, actor=actor)
        except (KeyError, ValueError, PermissionError):
            return

    def mentions_in(self, text: str) -> list[str]:
        """Ids of known entities whose name or alias appears in the text."""
        if not self.enabled or not text:
            return []
        haystack = text.lower()
        found: list[str] = []
        for name, entity_id in self.names():
            if len(name) < 3 or entity_id in found:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(name.lower()) + r"(?![a-z0-9])"
            if re.search(pattern, haystack):
                found.append(entity_id)
        return found


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
