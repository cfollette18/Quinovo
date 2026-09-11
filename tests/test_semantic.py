from __future__ import annotations

from quinovo.entities import EntityIndex, is_generic, normalize_kind
from quinovo.kernel import open_kernel
from quinovo.semantic import (
    EXTRACTOR_VERSION,
    enrich_new_conversations,
    parse_extraction,
    pending_conversations,
    write_extraction,
)
from quinovo.workspace import WORLD_PACK

EXTRACTION = {
    "entities": [
        {"name": "Langfuse", "kind": "tool", "description": "LLM observability platform"},
        {"name": "the user", "kind": "person"},
        {"name": "Quinovo", "kind": "project"},
    ],
    "facts": [
        {"subject": "Quinovo", "predicate": "traces with", "object": "Langfuse", "confidence": 0.9},
        {"subject": "Langfuse", "predicate": "listens_on", "object": "localhost:3000", "confidence": 0.8},
        {"subject": "the system", "predicate": "did", "object": "something", "confidence": 0.9},
        {"subject": "Langfuse", "predicate": "maybe", "object": "guess", "confidence": 0.2},
    ],
    "memories": [{"text": "Prefers small focused commits.", "kind": "preference", "about": ["Quinovo"]}],
    "todos": [{"text": "Reload the Cursor MCP after the fix.", "about": ["Cursor"]}],
    "decisions": [{"choice": "Keep Langfuse self-hosted.", "context": "Cost.", "about": ["Langfuse"]}],
    "questions": [],
}


def _world(tmp_path):
    return open_kernel(WORLD_PACK, tmp_path / "sem.sqlite")


def test_generic_words_are_never_entities():
    assert is_generic("the user")
    assert is_generic("System")
    assert is_generic("If")
    assert not is_generic("Langfuse")
    assert normalize_kind("company") == "organization"
    assert normalize_kind("nonsense") == "concept"


def test_parse_extraction_drops_generic_and_low_confidence_rows():
    parsed = parse_extraction(EXTRACTION)
    assert [item["name"] for item in parsed["entities"]] == ["Langfuse", "Quinovo"]
    triples = {(f["subject"], f["predicate"], f["value"]) for f in parsed["facts"]}
    assert triples == {
        ("Quinovo", "traces_with", "Langfuse"),
        ("Langfuse", "listens_on", "localhost:3000"),
    }
    assert parsed["memories"][0]["about"] == ["Quinovo"]


def test_write_extraction_links_triples_to_entities(tmp_path):
    kernel = _world(tmp_path)
    kernel.save_turn("s", 1, "quinovo", "Quinovo traces with Langfuse.", actor="test")
    written = write_extraction(
        kernel, parse_extraction(EXTRACTION), conv_id="s:1", topic_id="quinovo", actor="test"
    )
    assert set(written["entities"]) == {"langfuse", "quinovo"}
    assert len(written["facts"]) == 2
    fact = kernel.get_object("Fact", written["facts"][0])
    assert fact["properties"]["subject"] == "Quinovo"
    assert fact["properties"]["value"] == "Langfuse"
    about_quinovo = kernel.search_around("Entity", "quinovo", "facts_about")["objects"]
    assert {item["id"] for item in about_quinovo} == {written["facts"][0]}
    pointing_at_langfuse = kernel.search_around("Entity", "langfuse", "facts_mentioning")["objects"]
    assert {item["id"] for item in pointing_at_langfuse} == {written["facts"][0]}
    mentioned = kernel.search_around("Conversation", "s:1", "entities")["objects"]
    assert {item["id"] for item in mentioned} >= {"langfuse", "quinovo"}
    todos_about_cursor = kernel.search_around("Entity", "cursor", "todos")["objects"]
    assert len(todos_about_cursor) == 1
    decisions = kernel.search_around("Entity", "langfuse", "decisions")["objects"]
    assert decisions[0]["properties"]["choice"] == "Keep Langfuse self-hosted."
    # Nothing generic became an Entity, and no Person was invented.
    assert kernel.store.get_object("Entity", "the-user") is None
    assert kernel.store.get_object("Entity", "system") is None
    assert {item.id for item in kernel.store.list_objects("Person")} == {"cfollette18", "hermes", "cursor"}


def test_same_triple_twice_is_one_fact(tmp_path):
    kernel = _world(tmp_path)
    kernel.save_turn("s", 1, "quinovo", "first", actor="test")
    kernel.save_turn("s", 2, "quinovo", "second", actor="test")
    first = write_extraction(kernel, parse_extraction(EXTRACTION), conv_id="s:1", topic_id="quinovo", actor="test")
    second = write_extraction(kernel, parse_extraction(EXTRACTION), conv_id="s:2", topic_id="quinovo", actor="test")
    assert second["facts"] == []
    assert len(kernel.store.list_objects("Fact")) == len(first["facts"])
    produced_by = kernel.search_around("Fact", first["facts"][0], "conversation")["objects"]
    assert {item["id"] for item in produced_by} == {"s:1", "s:2"}


def test_aliases_resolve_to_one_entity(tmp_path):
    kernel = _world(tmp_path)
    index = EntityIndex(kernel)
    first = index.ensure("Langfuse", kind="tool", actor="test")
    again = index.ensure("the langfuse project", kind="tool", actor="test")
    assert first == again == "langfuse"
    lower = index.ensure("LANGFUSE", actor="test")
    assert lower == "langfuse"
    entity = kernel.get_object("Entity", "langfuse")
    assert "langfuse project" in entity["properties"]["aliases"]


def test_remember_without_a_model_only_links_known_mentions(tmp_path):
    kernel = _world(tmp_path)
    EntityIndex(kernel).ensure("Langfuse", kind="tool", actor="test")
    body = kernel.remember("Set up Langfuse tracing for Bob today.", topic="quinovo", session_id="s1")
    assert body["mode"] == "mentions"
    assert body["written"]["entities"] == ["langfuse"]
    assert kernel.store.list_objects("Fact") == []
    assert kernel.store.get_object("Entity", "bob") is None
    conv = kernel.get_object("Conversation", body["conversation"])
    assert conv["properties"]["enriched"] == EXTRACTOR_VERSION


def test_tick_enriches_save_turn_without_agent_tick(tmp_path, monkeypatch):
    kernel = _world(tmp_path)
    monkeypatch.setattr(
        "quinovo.semantic.llm_extract",
        lambda text, **kwargs: parse_extraction(EXTRACTION),
    )
    kernel.save_turn("s9", 0, "quinovo", "Quinovo traces with Langfuse on localhost:3000.", actor="test")
    assert len(pending_conversations(kernel)) == 1
    result = kernel.tick()
    assert result["semantics"]["conversations"] >= 1
    assert result["semantics"]["facts"]
    assert result["semantics"]["mode"] == "llm"
    assert pending_conversations(kernel) == []


def test_enrichment_is_idempotent(tmp_path):
    kernel = _world(tmp_path)
    kernel.remember("Nothing much happened.", topic="quinovo", session_id="s1")
    before = len(kernel.store.list_objects("Fact"))
    second = enrich_new_conversations(kernel)
    assert second["conversations"] == 0
    assert len(kernel.store.list_objects("Fact")) == before


def test_save_turn_fact_with_subject_links_entities(tmp_path):
    kernel = _world(tmp_path)
    EntityIndex(kernel).ensure("Epicor", kind="system", actor="test")
    kernel.save_turn(
        "s", 1, "cretex",
        "Ivanti feeds Epicor.",
        facts=[{"subject": "Ivanti", "predicate": "feeds", "object": "Epicor"}],
        todos=[{"text": "Ask for Epicor test access.", "about": ["Epicor"]}],
        actor="test",
    )
    fact = kernel.get_object("Fact", "fact_s:1_1")
    assert fact["properties"]["subject"] == "Ivanti"
    assert fact["properties"]["value"] == "Epicor"
    assert kernel.search_around("Fact", "fact_s:1_1", "subject_entity")["objects"][0]["id"] == "ivanti"
    assert kernel.search_around("Fact", "fact_s:1_1", "object_entity")["objects"][0]["id"] == "epicor"
    assert kernel.search_around("Entity", "epicor", "todos")["objects"][0]["id"] == "todo_s:1_1"


def test_empty_text_is_rejected(tmp_path):
    kernel = _world(tmp_path)
    try:
        kernel.remember("   ", topic="gifts")
    except ValueError:
        return
    raise AssertionError("empty remember should raise ValueError")
