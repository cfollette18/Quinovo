from fastapi.testclient import TestClient


def test_inference_is_not_just_stored_links(client: TestClient):
    client.post(
        "/ai/forecasts",
        json={
            "object_type": "Package",
            "id": "1Z999",
            "metric": "late_risk",
            "horizon_hours": 24,
            "point": 0.4,
            "model": "timesfm-2.5",
            "confidence": 0.88,
        },
    )
    ran = client.post("/inference/run")
    assert ran.status_code == 200
    predicates = {f["predicate"] for f in ran.json()["facts"]}
    assert "at_risk" in predicates
    assert "recommended_action" in predicates

    box = client.get("/objects/Package/1Z999").json()
    inferred = {f["predicate"]: f for f in box["inferred"]}
    assert inferred["at_risk"]["value"] == "true"
    assert inferred["at_risk"]["provenance"] == "predicted"
    assert inferred["at_risk"]["status"] == "asserted"
    assert inferred["recommended_action"]["value"].startswith("notify_buyer:")
    assert "bob" in inferred["recommended_action"]["value"]
    assert box["properties"]["status"] == "in_transit"


def test_low_confidence_forecast_parks_inference_for_hitl(client: TestClient):
    client.post(
        "/ai/forecasts",
        json={
            "object_type": "Package",
            "id": "1Z999",
            "metric": "late_risk",
            "horizon_hours": 24,
            "point": 0.5,
            "model": "timesfm-2.5",
            "confidence": 0.4,
        },
    )
    ran = client.post("/inference/run").json()
    at_risk = next(f for f in ran["facts"] if f["predicate"] == "at_risk")
    assert at_risk["hitl"] is True
    assert at_risk["status"] == "pending"

    approved = client.post(
        f"/inference/facts/{at_risk['id']}/approve",
        json={"actor": "dispatcher"},
    )
    assert approved.json()["fact"]["status"] == "asserted"
    box = client.get("/objects/Package/1Z999").json()
    inferred = {f["predicate"]: f for f in box["inferred"]}
    assert inferred["recommended_action"]["value"].startswith("notify_buyer:")
    assert inferred["recommended_action"]["status"] == "asserted"


def test_tracking_prefix_infers_amazon_without_seeded_link(client: TestClient):
    created = client.post(
        "/ai/classify",
        json={
            "object_type": "Package",
            "properties": {"id": "1ZNEW", "status": "in_transit"},
            "confidence": 0.95,
        },
    )
    assert created.status_code == 200
    assert client.get("/objects/Package/1ZNEW/links/shipper").json()["objects"] == []

    client.post("/inference/run")
    shipper = client.get("/objects/Package/1ZNEW/links/shipper").json()["objects"]
    assert shipper[0]["id"] == "amazon"

    box = client.get("/objects/Package/1ZNEW").json()
    link_facts = [f for f in box["inferred"] if f["predicate"] == "link:shipped_by"]
    assert link_facts[0]["value"] == "Company:amazon"
    assert link_facts[0]["status"] == "asserted"
