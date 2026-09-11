from __future__ import annotations

from datetime import UTC, datetime, timedelta

from quinovo.kernel import open_kernel
from quinovo.recall import describe, fact_sentence
from quinovo.workspace import WORLD_PACK


def _world(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "recall.sqlite")
    kernel.save_turn(
        "s",
        1,
        "quinovo",
        "Wired Langfuse tracing into the Quinovo loop.",
        facts=[
            {"subject": "Quinovo", "predicate": "traces_with", "value": "Langfuse"},
            {"subject": "Langfuse", "predicate": "listens_on", "value": "localhost:3000"},
        ],
        decisions=[
            {"choice": "Keep Langfuse self-hosted.", "context": "Cost.", "about": ["Langfuse"]}
        ],
        todos=[{"text": "Rotate the Langfuse key.", "about": ["Langfuse"]}],
        memories=[{"text": "Prefers small focused commits.", "kind": "preference"}],
        actor="test",
    )
    kernel.save_turn(
        "s",
        2,
        "cretex/technology",
        "Mapped the Epicor user termination flow.",
        facts=[{"subject": "Epicor", "predicate": "hosts", "value": "the ERP for Cretex"}],
        questions=[{"text": "Who owns Epicor licensing?", "about": ["Epicor"]}],
        actor="test",
    )
    return kernel


def test_fact_sentence_reads_like_prose():
    assert fact_sentence("Langfuse", "runs_on", "Docker") == "Langfuse runs on Docker"
    assert fact_sentence("", "decided", "ship it") == "Decided: ship it"


def test_recall_ranks_matching_objects_as_lines(tmp_path):
    kernel = _world(tmp_path)
    result = kernel.recall("langfuse")
    assert result["total"] >= 4
    lines = [hit["line"] for hit in result["hits"]]
    assert "Quinovo traces with Langfuse" in lines
    assert any(line.startswith("Decided: Keep Langfuse self-hosted.") for line in lines)
    assert all({"type", "id", "line", "topic"} <= set(hit) for hit in result["hits"])
    assert result["hits"][0]["type"] in {"Entity", "Fact"}


def test_recall_scopes_to_topic_and_types(tmp_path):
    kernel = _world(tmp_path)
    scoped = kernel.recall("epicor", topic="cretex")
    assert scoped["total"] >= 2
    for hit in scoped["hits"]:
        if hit["type"] == "Topic":
            assert hit["id"] in {
                "cretex",
                "technology",
                "epicor",
                "epicor-user-termination",
                "ticket-automation",
            }
        else:
            assert hit["topic"] == "technology"
    assert not any(hit["topic"] == "quinovo" for hit in scoped["hits"])
    only_questions = kernel.recall("epicor", types=["OpenQuestion"])
    assert {hit["type"] for hit in only_questions["hits"]} == {"OpenQuestion"}
    assert kernel.recall("", limit=5) == {"query": "", "hits": [], "total": 0}
    assert len(kernel.recall("langfuse", limit=1)["hits"]) == 1


def test_about_entity_walks_both_directions(tmp_path):
    kernel = _world(tmp_path)
    view = kernel.about("langfuse")
    assert view["kind"] == "entity"
    assert "Langfuse listens on localhost:3000" in view["facts"]
    assert "Quinovo traces with Langfuse" in view["mentioned_in_facts"]
    assert [e["id"] for e in view["related_entities"]] == ["quinovo"]
    assert view["todos"][0]["line"] == "Todo (open): Rotate the Langfuse key."
    assert view["decisions"][0]["line"].startswith("Decided: Keep Langfuse self-hosted.")
    assert view["counts"] == {"facts": 1, "mentioned_in_facts": 1, "conversations": 0}


def test_about_topic_and_unknown_name(tmp_path):
    kernel = _world(tmp_path)
    topic = kernel.about("cretex/technology")
    assert topic["kind"] == "topic"
    assert topic["parent"] == "cretex"
    assert topic["open_questions"][0]["line"] == "Question (open): Who owns Epicor licensing?"
    assert "Epicor hosts the ERP for Cretex" in topic["facts"]
    missing = kernel.about("nothing-like-this")
    assert missing["kind"] == "none"
    assert missing["suggestions"] == []


def test_briefing_is_one_bounded_page(tmp_path):
    kernel = _world(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    kernel.upsert_object(
        "Todo",
        {"id": "todo-old", "text": "Ancient chore.", "status": "open", "recorded_at": old},
        actor="test",
    )
    kernel.set_link("todo_in_topic", "todo-old", "quinovo", actor="test")
    kernel.run_inference()
    page = kernel.briefing(limit=3)
    assert page["pack"] == "world"
    assert page["topics"][0]["id"] in {"quinovo", "technology"}
    assert len(page["topics"]) <= 3
    todos = page["open_todos"]
    assert todos[0]["id"] == "todo-old" and todos[0]["stale"] is True
    assert page["open_questions"][0]["line"] == "Question (open): Who owns Epicor licensing?"
    assert page["memories"][0]["line"] == "Memory (preference): Prefers small focused commits."
    assert page["entities"][0]["id"] in {"langfuse", "quinovo", "epicor"}
    assert page["last_turn_at"]
    assert set(page["waiting_on_human"]) == {"proposals", "inferred_facts", "actions"}
    assert page["counts"]["Fact"] == 3


def test_describe_never_dumps_properties(tmp_path):
    kernel = _world(tmp_path)
    for type_name in ("Fact", "Todo", "Decision", "Memory", "Conversation", "Entity", "Topic"):
        for obj in kernel.store.list_objects(type_name):
            line = describe(kernel, obj)
            assert "{" not in line and "properties" not in line
            assert line.strip()
