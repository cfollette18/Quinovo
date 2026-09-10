from __future__ import annotations

from quinovo.kernel import open_kernel
from quinovo.semantic import enrich_new_conversations, extract_claims
from quinovo.workspace import WORLD_PACK

TEXT = "Bob delivers a package that contains lipstick to Jerry."


def test_extract_claims_sees_what_a_human_sees():
    claims = extract_claims(TEXT)
    values = " ".join(item["value"] for item in claims).lower()
    assert "bob" in values
    assert "jerry" in values
    assert "lipstick" in values
    assert "cosmetic" in values  # lipstick is_a cosmetic
    assert any(item["predicate"] == "recipient" for item in claims)
    assert any(item["predicate"] == "contains" for item in claims)
    assert any(item["predicate"] == "knows" for item in claims)
    assert any(item["predicate"] == "possesses" for item in claims)


def test_remember_writes_linked_knowledge(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "sem.sqlite")
    body = kernel.remember(TEXT, topic="gifts", session_id="s1")
    assert body["topic"] == "gifts"
    assert body["written"]["facts"]
    values = " ".join(
        kernel.get_object("Fact", fact_id)["properties"]["value"]
        for fact_id in body["written"]["facts"]
    ).lower()
    assert "lipstick" in values
    assert "jerry" in values
    # Persons are resolved for the human actors.
    persons = {item["id"] for item in kernel.store.list_objects("Person")}
    assert "bob" in persons
    assert "jerry" in persons


def test_tick_enriches_save_turn_without_agent_tick(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "sem.sqlite")
    kernel.save_turn("s9", 0, "gifts", TEXT)
    # The agent never called tick or remember; the loop still enriches.
    result = kernel.tick()
    assert result["semantics"]["conversations"] >= 1
    assert result["semantics"]["facts"]


def test_enrichment_is_idempotent(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "sem.sqlite")
    kernel.remember(TEXT, topic="gifts", session_id="s1")
    before = len(kernel.store.list_objects("Fact"))
    second = enrich_new_conversations(kernel)
    assert second["facts"] == []
    assert len(kernel.store.list_objects("Fact")) == before


def test_empty_text_is_rejected(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "sem.sqlite")
    try:
        kernel.remember("   ", topic="gifts")
    except ValueError:
        return
    raise AssertionError("empty remember should raise ValueError")
