from __future__ import annotations

from fastapi.testclient import TestClient

from quinovo.language.load import load_ontology


def test_ontology_loads():
    ont = load_ontology("packs/example/ontology.yaml")
    assert ont.ontology.api_name == "example"
    assert {t.api_name for t in ont.object_types} == {
        "Package",
        "Product",
        "Person",
        "Company",
    }
    assert {t.api_name for t in ont.link_types} == {
        "contains",
        "destined_for",
        "shipped_by",
    }
    assert ont.action_type("mark_delivered").api_name == "mark_delivered"
    assert ont.action_type("notify_buyer").mcp_requires_recommendation is True


def test_package_story_links(client: TestClient):
    box = client.get("/objects/Package/1Z999")
    assert box.status_code == 200
    assert box.json()["properties"]["status"] == "in_transit"

    product = client.get("/objects/Package/1Z999/links/product")
    assert product.json()["objects"][0]["id"] == "lipstick-1"

    buyer = client.get("/objects/Package/1Z999/links/buyer")
    assert buyer.json()["objects"][0]["id"] == "bob"

    shipper = client.get("/objects/Package/1Z999/links/shipper")
    assert shipper.json()["objects"][0]["id"] == "amazon"

    bobs_boxes = client.get("/objects/Person/bob/links/packages")
    assert bobs_boxes.json()["objects"][0]["id"] == "1Z999"


def test_mark_delivered_is_audited(client: TestClient):
    applied = client.post(
        "/actions/mark_delivered",
        json={"parameters": {"package": {"id": "1Z999"}}, "actor": "warehouse-agent"},
    )
    assert applied.status_code == 200
    assert applied.json()["objects"][0]["properties"]["status"] == "delivered"

    after = client.get("/objects/Package/1Z999").json()
    assert after["properties"]["status"] == "delivered"

    audit = client.get("/audit").json()["entries"]
    assert len(audit) == 1
    assert audit[0]["action_type"] == "mark_delivered"
    assert audit[0]["actor"] == "warehouse-agent"


def test_unknown_action_rejected(client: TestClient):
    response = client.post("/actions/patch_row", json={"parameters": {}})
    assert response.status_code == 400
