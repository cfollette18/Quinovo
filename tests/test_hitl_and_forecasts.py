from fastapi.testclient import TestClient


def test_classify_auto_applies_at_90_percent(client: TestClient):
    response = client.post(
        "/ai/classify",
        json={
            "object_type": "Package",
            "properties": {"id": "1Z888", "status": "in_transit"},
            "confidence": 0.9,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hitl"] is False
    assert body["proposal"]["status"] == "auto_applied"
    found = client.get("/objects/Package/1Z888")
    assert found.status_code == 200


def test_classify_below_80_percent_needs_human(client: TestClient):
    response = client.post(
        "/ai/classify",
        json={
            "object_type": "Package",
            "properties": {"id": "1Z777", "status": "in_transit"},
            "confidence": 0.5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hitl"] is True
    assert body["proposal"]["status"] == "pending"
    assert client.get("/objects/Package/1Z777").status_code == 404

    proposal_id = body["proposal"]["id"]
    approved = client.post(
        f"/proposals/{proposal_id}/approve",
        json={"actor": "bob"},
    )
    assert approved.status_code == 200
    assert client.get("/objects/Package/1Z777").status_code == 200


def test_new_type_auto_then_classify(client: TestClient):
    proposed = client.post(
        "/ai/types",
        json={
            "confidence": 0.86,
            "type_def": {
                "api_name": "Return",
                "primary_key": "id",
                "title_property": "id",
                "properties": [
                    {"api_name": "id", "type": "string"},
                    {"api_name": "reason", "type": "string"},
                ],
            },
        },
    )
    assert proposed.status_code == 200
    assert proposed.json()["hitl"] is False
    types = {t["api_name"] for t in client.get("/ontology").json()["object_types"]}
    assert "Return" in types

    classified = client.post(
        "/ai/classify",
        json={
            "object_type": "Return",
            "properties": {"id": "r-1", "reason": "wrong shade"},
            "confidence": 0.95,
        },
    )
    assert classified.status_code == 200
    assert client.get("/objects/Return/r-1").json()["properties"]["reason"] == "wrong shade"


def test_new_type_low_confidence_is_hitl(client: TestClient):
    proposed = client.post(
        "/ai/types",
        json={
            "confidence": 0.4,
            "type_def": {
                "api_name": "Warehouse",
                "primary_key": "id",
                "title_property": "name",
                "properties": [
                    {"api_name": "id", "type": "string"},
                    {"api_name": "name", "type": "string"},
                ],
            },
        },
    )
    assert proposed.json()["hitl"] is True
    types = {t["api_name"] for t in client.get("/ontology").json()["object_types"]}
    assert "Warehouse" not in types

    proposal_id = proposed.json()["proposal"]["id"]
    client.post(f"/proposals/{proposal_id}/approve", json={"actor": "human"})
    types = {t["api_name"] for t in client.get("/ontology").json()["object_types"]}
    assert "Warehouse" in types


def test_forecast_lives_on_the_package(client: TestClient):
    written = client.post(
        "/ai/forecasts",
        json={
            "object_type": "Package",
            "id": "1Z999",
            "metric": "late_risk",
            "horizon_hours": 24,
            "point": 0.31,
            "q10": 0.1,
            "q90": 0.55,
            "model": "timesfm-2.5",
            "confidence": 0.88,
        },
    )
    assert written.status_code == 200
    assert written.json()["forecast"]["actionable"] is True

    box = client.get("/objects/Package/1Z999").json()
    assert box["forecasts"][0]["metric"] == "late_risk"
    assert box["forecasts"][0]["model"] == "timesfm-2.5"

    uncertain = client.post(
        "/ai/forecasts",
        json={
            "object_type": "Package",
            "id": "1Z999",
            "metric": "late_risk",
            "horizon_hours": 72,
            "point": 0.7,
            "model": "timesfm-2.5",
            "confidence": 0.4,
        },
    )
    assert uncertain.json()["forecast"]["actionable"] is False
