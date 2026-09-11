"""One-shot repair of a world database that an earlier extractor filled with noise.

What it removes, and why each is safe to remove:

- Facts written by the retired regex extractor (ids ``sem-*``). Their
  predicates (mentioned_with, is_a, contains, transfer, ...) came from a
  gift-delivery template, they have no subject, and the turns they came from
  are still here, so the model re-extracts them as proper triples.
- Memories the same extractor wrote (ids ``mem-*``), for the same reason.
- Persons named after stopwords or generic words ("After", "If", "Every"),
  plus Persons left with no links once the junk memories are gone. Real
  people come back as Entities when their turns are re-read.
- Inferred facts produced by rules that no longer exist in the pack (the
  auto-applied hash-prefix and status-restating rules), because there is no
  rule left to explain them.
- Pending proposals from the heuristic synthesizer (``synth_*``), which a
  human would have rejected one by one.
- Extra ``*_in_topic`` links a prefix rule bolted onto a Fact; a Fact lives
  in the topic of the turn that produced it.
- Topics the clusterer invented from noise, once they are empty.
- The ``enriched`` stamp on every Conversation, so the loop re-reads them.

Everything runs through the store so the audit trail records it. A backup
of the database is written first.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quinovo.ai.runtime import ProposalError
from quinovo.ai.runtime import reject_proposal as reject_stored_proposal
from quinovo.entities import is_generic
from quinovo.pack.seed import load_seed_doc
from quinovo.semantic import EXTRACTOR_VERSION
from quinovo.topics import PROTECTED_TOPICS, topic_children

JUNK_FACT_PREFIX = "sem-"
JUNK_MEMORY_PREFIX = "mem-"
# The current extractor also writes mem-<12 hex>; the retired one embedded the turn id.
CURRENT_MEMORY_ID = re.compile(r"^mem-[0-9a-f]{12}$")
JUNK_PROPOSAL_PREFIX = "synth_"
NOISE_TOPICS = frozenset({"harness", "model", "semantic"})
ACTOR = "quinovo-repair"


def _seeded_ids(kernel: Any, object_type: str) -> set[str]:
    """Objects the pack's seed.yaml creates on boot; deleting them only recreates them."""
    seed_path = Path(kernel.pack_dir) / "seed.yaml"
    if not seed_path.exists():
        return set()
    seed = load_seed_doc(seed_path)
    return {
        str(row.get(kernel.ontology.object_type(object_type).primary_key) or "")
        for row in seed.objects.get(object_type, [])
    }


def backup_database(db_path: Path) -> Path:
    """Consistent copy next to the database, even while another process writes."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.stem}-backup-{stamp}{db_path.suffix}")
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return dest


def _has_type(kernel: Any, api_name: str) -> bool:
    return any(item.api_name == api_name for item in kernel.ontology.object_types)


def _ids(kernel: Any, object_type: str, prefix: str) -> list[str]:
    if not _has_type(kernel, object_type):
        return []
    return [obj.id for obj in kernel.store.list_objects(object_type) if obj.id.startswith(prefix)]


def _junk_memories(kernel: Any) -> list[str]:
    return [
        memory_id
        for memory_id in _ids(kernel, "Memory", JUNK_MEMORY_PREFIX)
        if not CURRENT_MEMORY_ID.match(memory_id)
    ]


def _stale_stamps(kernel: Any) -> list[Any]:
    """Conversations stamped by an extractor other than the current one."""
    if not _has_type(kernel, "Conversation"):
        return []
    found = []
    for obj in kernel.store.list_objects("Conversation"):
        stamp = str((obj.properties or {}).get("enriched") or "")
        if stamp and stamp != EXTRACTOR_VERSION and not stamp.startswith("claim@"):
            found.append(obj)
    return found


def _orphan_rules(kernel: Any) -> dict[str, int]:
    live = {rule.api_name for rule in kernel.ruleset.rules} if kernel.ruleset else set()
    return {rule: n for rule, n in kernel.store.list_inferred_rules().items() if rule not in live}


def _junk_persons(kernel: Any) -> list[str]:
    if not _has_type(kernel, "Person"):
        return []
    linked: set[str] = set()
    for link in kernel.store.list_all_links():
        if link.from_type == "Person":
            linked.add(link.from_id)
        if link.to_type == "Person":
            linked.add(link.to_id)
    keep = _seeded_ids(kernel, "Person")
    junk: list[str] = []
    for obj in kernel.store.list_objects("Person"):
        if obj.id in keep:
            continue
        name = str((obj.properties or {}).get("name") or obj.id)
        if is_generic(name) or is_generic(obj.id.replace("-", " ")) or obj.id not in linked:
            junk.append(obj.id)
    return junk


def _junk_proposals(kernel: Any) -> list[int]:
    found: list[int] = []
    for proposal in kernel.store.list_proposals("pending"):
        name = str((proposal.payload or {}).get("api_name") or "")
        if name.startswith(JUNK_PROPOSAL_PREFIX):
            found.append(proposal.id)
    return found


def _extra_topic_links(kernel: Any) -> list[tuple[str, str, str]]:
    """(link_type, fact_id, topic_id) for every fact_in_topic beyond the producing turn's topic."""
    if not _has_type(kernel, "Fact") or not _has_type(kernel, "Topic"):
        return []
    fact_topics: dict[str, list[str]] = defaultdict(list)
    conv_topic: dict[str, str] = {}
    produced_by: dict[str, str] = {}
    for link in kernel.store.list_all_links():
        if link.link_type == "fact_in_topic":
            fact_topics[link.from_id].append(link.to_id)
        elif link.link_type == "conversation_in_topic":
            conv_topic[link.from_id] = link.to_id
        elif link.link_type == "produced":
            produced_by[link.to_id] = link.from_id
    extra: list[tuple[str, str, str]] = []
    for fact_id, topics in fact_topics.items():
        if len(topics) < 2:
            continue
        home = conv_topic.get(produced_by.get(fact_id, ""), "")
        keep = home if home in topics else min(topics)
        extra.extend(("fact_in_topic", fact_id, t) for t in topics if t != keep)
    return extra


def _empty_noise_topics(kernel: Any) -> list[str]:
    if not _has_type(kernel, "Topic"):
        return []
    occupied: set[str] = set()
    for link in kernel.store.list_all_links():
        if link.to_type == "Topic" and link.link_type != "subtopic_of":
            occupied.add(link.to_id)
    return [
        obj.id
        for obj in kernel.store.list_objects("Topic")
        if obj.id in NOISE_TOPICS
        and obj.id not in PROTECTED_TOPICS
        and obj.id not in occupied
        and not topic_children(kernel, obj.id)
    ]


def plan(kernel: Any) -> dict[str, Any]:
    """What repair would do, without doing it."""
    return {
        "facts": _ids(kernel, "Fact", JUNK_FACT_PREFIX),
        "memories": _junk_memories(kernel),
        "persons": _junk_persons(kernel),
        "orphan_rules": _orphan_rules(kernel),
        "proposals": _junk_proposals(kernel),
        "extra_topic_links": _extra_topic_links(kernel),
        "conversations": len(_stale_stamps(kernel)),
    }


def repair(kernel: Any, *, actor: str = ACTOR, backup: bool = True) -> dict[str, Any]:
    """Clean the database in place. Returns what was removed."""
    backup_path: Path | None = None
    if backup:
        backup_path = backup_database(Path(kernel.store.db_path))

    todo = plan(kernel)
    removed: dict[str, int] = {}

    for fact_id in todo["facts"]:
        kernel.store.delete_object("Fact", fact_id)
    removed["facts"] = len(todo["facts"])

    for memory_id in todo["memories"]:
        kernel.store.delete_object("Memory", memory_id)
    removed["memories"] = len(todo["memories"])

    # Persons are judged after the junk memories are gone, so orphans show.
    persons = _junk_persons(kernel)
    for person_id in persons:
        kernel.store.delete_object("Person", person_id)
    removed["persons"] = len(persons)

    removed["inferred_facts"] = sum(
        kernel.store.delete_inferred_facts_by_rule(rule) for rule in todo["orphan_rules"]
    )

    rejected = 0
    for proposal_id in todo["proposals"]:
        try:
            reject_stored_proposal(kernel, proposal_id, actor)
            rejected += 1
        except ProposalError:
            continue
    removed["proposals"] = rejected

    for link_type, fact_id, topic_id in _extra_topic_links(kernel):
        kernel.store.remove_link(link_type, "Fact", fact_id, "Topic", topic_id)
    removed["extra_topic_links"] = len(todo["extra_topic_links"])

    topics = _empty_noise_topics(kernel)
    for topic_id in topics:
        kernel.store.delete_object("Topic", topic_id)
    removed["topics"] = len(topics)

    stale = _stale_stamps(kernel)
    for obj in stale:
        props = dict(obj.properties or {})
        props.pop("enriched", None)
        kernel.store.upsert_object("Conversation", props, source="action")
    removed["conversations_reset"] = len(stale)

    kernel.store.append_audit("repair", actor, {"removed": removed}, "applied")
    kernel.nudge()
    return {"backup": str(backup_path) if backup_path else "", "removed": removed}
