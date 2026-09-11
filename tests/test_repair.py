from __future__ import annotations

from quinovo.kernel import open_kernel
from quinovo.repair import plan, repair
from quinovo.workspace import WORLD_PACK


def _polluted(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "world.sqlite")
    kernel.save_turn(
        "s",
        1,
        "quinovo",
        "Real turn.",
        facts=[{"subject": "Langfuse", "predicate": "runs_on", "value": "Docker"}],
        memories=[{"text": "Prefers small commits.", "kind": "preference"}],
        actor="test",
    )
    conv = kernel.store.get_object("Conversation", "s:1")
    kernel.store.upsert_object(
        "Conversation", {**conv.properties, "enriched": "v1"}, source="action"
    )
    now = "2026-09-01T00:00:00+00:00"
    for i in range(3):
        kernel.upsert_object(
            "Fact",
            {
                "id": f"sem-abc{i}",
                "predicate": "mentioned_with",
                "value": f"Noise {i}.",
                "confidence": 0.8,
                "recorded_at": now,
            },
            actor="test",
        )
        kernel.set_link("fact_in_topic", f"sem-abc{i}", "quinovo", actor="test")
    kernel.upsert_object(
        "Memory",
        {
            "id": "mem-1",
            "text": "The author knows.",
            "kind": "lesson",
            "confidence": 0.8,
            "recorded_at": now,
        },
        actor="test",
    )
    kernel.upsert_object(
        "Memory",
        {
            "id": "mem-0123456789ab",
            "text": "Written by the current extractor.",
            "kind": "lesson",
            "confidence": 0.8,
            "recorded_at": now,
        },
        actor="test",
    )
    kernel.save_turn("s", 2, "quinovo", "Already read by v2.", actor="test")
    conv2 = kernel.store.get_object("Conversation", "s:2")
    kernel.store.upsert_object(
        "Conversation", {**conv2.properties, "enriched": "v2"}, source="action"
    )
    for pid, name in (
        ("after", "After"),
        ("if", "If"),
        ("chris", "Chris"),
        ("cfollette18", "cfollette18"),
    ):
        kernel.upsert_object("Person", {"id": pid, "name": name}, actor="test")
    kernel.set_link("person_owns_memory", "chris", "mem-1", actor="test")
    kernel.store.upsert_inferred_fact(
        "Fact", "fact_s:1_1", "topic_fact", "true", 0.9, "fact_is_topic_fact", "rule", "asserted"
    )
    kernel.store.upsert_inferred_fact(
        "Fact", "fact_s:1_1", "stale", "true", 0.9, "todo_stale", "rule", "asserted"
    )
    kernel.propose(
        "inference_rule",
        {
            "api_name": "synth_prefix_Fact_sem_abc_fact_in_topic",
            "kind": "prefix_link",
            "description": "junk",
            "source_type": "Fact",
            "confidence": 0.9,
            "when_pk_prefix": "sem-abc",
            "then_link": {"link_type": "fact_in_topic", "to_type": "Topic", "to_id": "quinovo"},
        },
        0.6,
        actor="quinovo-synth",
    )
    kernel.propose(
        "link_type",
        {
            "api_name": "cites_source",
            "description": "keep me",
            "reason": "human wants it",
            "from_type": "Fact",
            "to_type": "Topic",
            "from_name": "cites",
            "to_name": "cited_by",
        },
        0.5,
        actor="quinovo-ai",
    )
    kernel.upsert_object("Topic", {"id": "harness", "name": "Harness"}, actor="test")
    kernel.upsert_object("Topic", {"id": "langfuse", "name": "Langfuse"}, actor="test")
    kernel.set_link("fact_in_topic", "fact_s:1_1", "langfuse", actor="test")
    return kernel


def test_plan_names_only_the_noise(tmp_path):
    kernel = _polluted(tmp_path)
    todo = plan(kernel)
    assert sorted(todo["facts"]) == ["sem-abc0", "sem-abc1", "sem-abc2"]
    assert todo["memories"] == ["mem-1"]
    assert set(todo["persons"]) == {"after", "if"}
    assert todo["orphan_rules"] == {"fact_is_topic_fact": 1}
    assert len(todo["proposals"]) == 1
    assert todo["extra_topic_links"] == [("fact_in_topic", "fact_s:1_1", "langfuse")]
    assert todo["conversations"] == 1


def test_repair_removes_noise_and_keeps_real_knowledge(tmp_path):
    kernel = _polluted(tmp_path)
    result = repair(kernel, backup=True)
    removed = result["removed"]
    assert removed == {
        "facts": 3,
        "memories": 1,
        "persons": 3,
        "inferred_facts": 1,
        "proposals": 1,
        "extra_topic_links": 1,
        "topics": 1,
        "conversations_reset": 1,
    }
    assert (tmp_path / result["backup"].split("/")[-1]).exists()
    assert kernel.store.get_object("Fact", "fact_s:1_1") is not None
    assert kernel.store.get_object("Memory", "memory_s:1_1") is not None
    assert kernel.store.get_object("Memory", "mem-0123456789ab") is not None
    assert kernel.store.get_object("Conversation", "s:2").properties["enriched"] == "v2"
    assert kernel.store.get_object("Person", "cfollette18") is not None
    assert kernel.store.get_object("Person", "chris") is None
    assert kernel.store.get_object("Topic", "harness") is None
    assert kernel.store.get_object("Topic", "langfuse") is not None
    assert [f.rule for f in kernel.store.list_inferred_facts("Fact", "fact_s:1_1")] == [
        "todo_stale"
    ]
    pending = {p.kind for p in kernel.store.list_proposals("pending")}
    assert pending == {"link_type"}
    assert "enriched" not in kernel.store.get_object("Conversation", "s:1").properties
    topics = [l.to_id for l in kernel.store.list_all_links() if l.link_type == "fact_in_topic"]
    assert topics == ["quinovo"]
    assert plan(kernel) == {
        "facts": [],
        "memories": [],
        "persons": [],
        "orphan_rules": {},
        "proposals": [],
        "extra_topic_links": [],
        "conversations": 0,
    }
