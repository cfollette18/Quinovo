from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from quinovo.connectors.transcripts import parse_transcript, topic_for_path
from quinovo.kernel import open_kernel
from quinovo.workspace import WORLD_PACK


def _world(tmp_path):
    return open_kernel(WORLD_PACK, tmp_path / "world.sqlite")


def test_seed_creates_cretex_subtopics(tmp_path):
    kernel = _world(tmp_path)
    cretex = kernel.get_object("Topic", "cretex")
    assert cretex["properties"]["name"] == "Cretex"
    children = {
        item["id"]
        for item in kernel.search_around("Topic", "cretex", "subtopics")["objects"]
    }
    assert children == {"technology", "workflows", "mcp-servers"}
    tech = {
        item["id"]
        for item in kernel.search_around("Topic", "technology", "subtopics")["objects"]
    }
    assert tech == {"ivanti", "epicor", "jira"}
    planned = {
        item["id"]
        for item in kernel.search_around("Topic", "workflows", "subtopics")["objects"]
    }
    assert planned == {
        "ticket-automation",
        "epicor-user-termination",
        "documentation-automation",
        "faq-bot",
    }


def test_save_turn_creates_missing_topic_and_links(tmp_path):
    kernel = _world(tmp_path)
    body = kernel.save_turn(
        "sess-1",
        1,
        "cretex/workflows",
        "Wired Cursor to Quinovo and started Cretex capture.",
        role="debug",
        facts=[{"id": "fact_cursor_mcp", "predicate": "connected", "value": "cursor-mcp"}],
        decisions=[
            {
                "id": "dec_cretex_tree",
                "choice": "File Cretex work under technology and workflows subtopics.",
                "context": "User asked for packs inside the Cretex topic.",
            }
        ],
        todos=[{"id": "todo_reload_mcp", "text": "Reload Cursor MCP after capture fix."}],
        memories=[
            {
                "id": "mem_save_every_turn",
                "text": "Every agent turn must call save_turn.",
                "kind": "lesson",
            }
        ],
        actor="test",
    )
    assert body["topic"] == "workflows"
    conv = kernel.get_object("Conversation", "sess-1:1")
    assert conv["properties"]["summary"].startswith("Wired Cursor")
    facts = kernel.search_around("Conversation", "sess-1:1", "facts")["objects"]
    assert {item["id"] for item in facts} == {"fact_cursor_mcp"}
    topic_facts = kernel.search_around("Topic", "workflows", "facts")["objects"]
    assert {item["id"] for item in topic_facts} == {"fact_cursor_mcp"}


def test_save_turn_creates_brand_new_topic(tmp_path):
    kernel = _world(tmp_path)
    body = kernel.save_turn(
        "sess-2",
        1,
        "brand-new-client",
        "Invented a topic on the fly.",
        actor="test",
    )
    assert body["topic"] == "brand-new-client"
    obj = kernel.get_object("Topic", "brand-new-client")
    assert obj["properties"]["status"] == "active"


def test_open_todo_older_than_two_weeks_is_stale(tmp_path):
    kernel = _world(tmp_path)
    old = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    kernel.save_turn(
        "sess-3",
        1,
        "quinovo",
        "Two todos, one forgotten.",
        todos=[
            {"id": "todo_old", "text": "Forgotten work.", "recorded_at": old},
            {"id": "todo_new", "text": "Fresh work."},
        ],
        actor="test",
    )
    kernel.run_inference()
    old_box = kernel.get_object("Todo", "todo_old")
    predicates = {fact["predicate"]: fact for fact in old_box["facts"]}
    assert predicates["stale"]["value"] == "true"
    assert predicates["stale"]["status"] == "asserted"
    assert predicates["stale"]["provenance_detail"]["age_days"] >= 20
    fresh = kernel.get_object("Todo", "todo_new")
    assert not any(fact["predicate"] == "stale" for fact in fresh["facts"])


def test_transcripts_source_files_under_cretex_path(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "cap.sqlite")
    folder = tmp_path / "cretex-automation" / "agent-transcripts" / "abc"
    folder.mkdir(parents=True)
    transcript = folder / "abc.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "<user_query>\nbuild the ivanti mcp\n</user_query>",
                        }
                    ]
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "role": "assistant",
                "message": {"content": [{"type": "text", "text": "Starting the Ivanti MCP scaffold."}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    parsed = parse_transcript(transcript)
    assert parsed is not None
    assert "build the ivanti mcp" in parsed["summary"]
    assert topic_for_path(transcript, {"cretex-automation": "workflows"}, "quinovo") == "workflows"
    kernel.register_source(
        "local-transcripts",
        "transcripts",
        "Conversation",
        {"globs": [str(transcript)], "path_topics": {"cretex-automation": "workflows"}},
        auto=False,
    )
    pulled = kernel.pull_source("local-transcripts")
    assert pulled["count"] == 1
    linked = kernel.search_around("Topic", "workflows", "contents")["objects"]
    assert any(item["id"].startswith("cursor:abc") for item in linked)
    again = kernel.pull_source("local-transcripts")
    assert again["count"] == 0


def test_graph_payload_exposes_edges(tmp_path):
    kernel = _world(tmp_path)
    graph = kernel.graph()
    assert graph["edges"]
    assert {edge["type"] for edge in graph["edges"]} >= {"subtopic_of"}
    sample = graph["edges"][0]
    assert "from" in sample and "to" in sample
    assert graph["nodes"][0].get("pk")


def test_tick_does_not_crash_on_world_pack(tmp_path):
    kernel = _world(tmp_path)
    body = kernel.tick()
    assert "pending_facts" in body
    assert "sources_pulled" in body
