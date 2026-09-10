from __future__ import annotations

from datetime import UTC, datetime

from quinovo.apps.schema_manager import schema_manager_html
from quinovo.kernel import open_kernel
from quinovo.topics import catalog_topics, organize_topics
from quinovo.workspace import WORLD_PACK


def _world(tmp_path):
    return open_kernel(WORLD_PACK, tmp_path / "world.sqlite")


def test_catalog_page_shows_topic_baskets(tmp_path):
    kernel = _world(tmp_path)
    catalog = kernel.catalog_data()
    text = schema_manager_html(kernel.ontology, catalog["counts"], topics=catalog["topics"])
    assert "Catalog" in text
    assert "Organize with AI" in text
    assert "Cretex" in text
    assert "MCP servers" in text
    assert "Technology" in text
    assert "Workflows" in text
    assert "A topic is a basket" in text
    assert "json-panel" not in text
    assert "<pre" not in text
    assert 'id="topic-cretex"' in text


def test_organize_recreates_missing_mcp_servers_under_cretex(tmp_path):
    kernel = _world(tmp_path)
    kernel.delete_object("Topic", "mcp-servers", actor="test")
    result = organize_topics(kernel, "test")
    assert "mcp-servers" in result["created"]
    children = {
        item["id"]
        for item in kernel.search_around("Topic", "cretex", "subtopics")["objects"]
    }
    assert "mcp-servers" in children
    obj = kernel.get_object("Topic", "mcp-servers")
    assert obj["properties"]["name"] == "MCP servers"


def test_organize_nests_fruit_style_orphans(tmp_path):
    kernel = _world(tmp_path)
    kernel.upsert_object(
        "Topic",
        {"id": "fruit", "name": "Fruit", "status": "active"},
        actor="test",
    )
    kernel.upsert_object(
        "Topic",
        {"id": "tropical-fruit", "name": "Tropical fruit", "status": "active"},
        actor="test",
    )
    kernel.upsert_object(
        "Topic",
        {
            "id": "orange-tropical-fruit",
            "name": "Orange tropical fruit",
            "status": "active",
        },
        actor="test",
    )
    organize_topics(kernel, "test")
    assert kernel.search_around("Topic", "tropical-fruit", "parent")["objects"][0]["id"] == "fruit"
    assert (
        kernel.search_around("Topic", "orange-tropical-fruit", "parent")["objects"][0]["id"]
        == "tropical-fruit"
    )


def test_organize_clusters_similar_unfiled_facts(tmp_path):
    kernel = _world(tmp_path)
    now = datetime.now(UTC).isoformat()
    for index, label in enumerate(
        ("navel orange inventory", "blood orange shipment", "cara cara orange basket"),
        start=1,
    ):
        kernel.upsert_object(
            "Fact",
            {
                "id": f"fact_orange_{index}",
                "predicate": "mentions",
                "value": label,
                "confidence": 0.9,
                "recorded_at": now,
            },
            actor="test",
        )
    result = organize_topics(kernel, "test")
    assert "orange" in result["created"]
    filed = {item["id"] for item in kernel.search_around("Topic", "orange", "facts")["objects"]}
    assert filed == {"fact_orange_1", "fact_orange_2", "fact_orange_3"}


def test_catalog_topics_forest_includes_cretex_children(tmp_path):
    kernel = _world(tmp_path)
    forest = catalog_topics(kernel)
    by_id = {node["id"]: node for node in forest}
    assert "cretex" in by_id
    child_ids = {child["id"] for child in by_id["cretex"]["children"]}
    assert {"technology", "workflows", "mcp-servers"} <= child_ids
