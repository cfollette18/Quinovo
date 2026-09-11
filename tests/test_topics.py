from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from quinovo.api.app import create_app
from quinovo.apps.schema_manager import schema_manager_html
from quinovo.kernel import open_kernel
from quinovo.topics import CatalogError, catalog_topics, organize_topics
from quinovo.workspace import WORLD_PACK


def _world(tmp_path):
    return open_kernel(WORLD_PACK, tmp_path / "world.sqlite")


@pytest.mark.xfail(reason="catalog topic editing UI is not built yet", strict=False)
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
    assert "New topic" in text
    assert "Edit this topic" in text
    assert "Add topic" in text
    assert 'action="/catalog/topics"' in text
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
    assert by_id["cretex"]["parent_id"] == ""
    tech = next(child for child in by_id["cretex"]["children"] if child["id"] == "technology")
    assert tech["parent_id"] == "cretex"


def test_catalog_creates_updates_and_deletes_topics(tmp_path):
    kernel = _world(tmp_path)
    created = kernel.create_topic(
        "Citrus grove",
        description="Oranges and kin",
        parent="cretex",
        actor="test",
    )
    assert created["id"] == "citrus-grove"
    obj = kernel.get_object("Topic", "citrus-grove")
    assert obj["properties"]["name"] == "Citrus grove"
    assert obj["properties"]["description"] == "Oranges and kin"
    assert kernel.search_around("Topic", "citrus-grove", "parent")["objects"][0]["id"] == "cretex"

    kernel.update_topic(
        "citrus-grove",
        name="Citrus",
        description="Citrus fruit",
        parent="",
        actor="test",
    )
    updated = kernel.get_object("Topic", "citrus-grove")
    assert updated["properties"]["name"] == "Citrus"
    assert kernel.search_around("Topic", "citrus-grove", "parent")["objects"] == []

    kernel.update_topic("citrus-grove", status="archived", actor="test")
    assert kernel.get_object("Topic", "citrus-grove")["properties"]["status"] == "archived"

    kernel.delete_topic("citrus-grove", actor="test")
    with pytest.raises(KeyError):
        kernel.get_object("Topic", "citrus-grove")


def test_catalog_delete_moves_children_and_protects_workspace_topics(tmp_path):
    kernel = _world(tmp_path)
    kernel.create_topic("Grove", parent="cretex", actor="test")
    kernel.create_topic("Navel", parent="grove", actor="test")
    with pytest.raises(CatalogError, match="cannot sit inside"):
        kernel.update_topic("grove", parent="navel", actor="test")
    with pytest.raises(CatalogError, match="already exists"):
        kernel.create_topic("Cretex", actor="test")
    with pytest.raises(CatalogError, match="cannot be removed"):
        kernel.delete_topic("cretex", actor="test")
    kernel.delete_topic("grove", actor="test")
    with pytest.raises(KeyError):
        kernel.get_object("Topic", "grove")
    assert kernel.search_around("Topic", "navel", "parent")["objects"][0]["id"] == "cretex"


@pytest.mark.xfail(reason="catalog topic editing UI is not built yet", strict=False)
def test_catalog_topic_crud_http(tmp_path):
    app = create_app(pack_dir=WORLD_PACK, db_path=tmp_path / "world.sqlite")
    with TestClient(app) as client:
        page = client.get("/catalog")
        assert page.status_code == 200
        assert "New topic" in page.text
        assert "Edit this topic" in page.text
        assert 'action="/catalog/topics"' in page.text
        created = client.post(
            "/catalog/topics",
            data={"name": "Citrus grove", "description": "Oranges", "parent": "cretex"},
            follow_redirects=False,
        )
        assert created.status_code == 303
        location = created.headers["location"]
        assert "notice=created" in location
        assert "topic=citrus-grove" in location
        after_create = client.get("/catalog?topic=citrus-grove")
        assert after_create.status_code == 200
        assert "Citrus grove" in after_create.text
        assert "Remove" in after_create.text
        updated = client.post(
            "/catalog/topics/citrus-grove",
            data={
                "name": "Citrus",
                "description": "Citrus fruit",
                "parent": "",
                "status": "active",
            },
            follow_redirects=False,
        )
        assert updated.status_code == 303
        assert "notice=updated" in updated.headers["location"]
        archived = client.post(
            "/catalog/topics/citrus-grove",
            data={
                "name": "Citrus",
                "description": "Citrus fruit",
                "parent": "",
                "status": "archived",
            },
            follow_redirects=False,
        )
        assert archived.status_code == 303
        assert "notice=archived" in archived.headers["location"]
        deleted = client.post(
            "/catalog/topics/citrus-grove/delete",
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert "notice=deleted" in deleted.headers["location"]
        blocked = client.post(
            "/catalog/topics/cretex/delete",
            follow_redirects=False,
        )
        assert blocked.status_code == 303
        assert "error=" in blocked.headers["location"]
