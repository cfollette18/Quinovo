"""HTTP + workspace surfaces for connections, SDK, and the contract."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_sources_page_renders(client: TestClient):
    page = client.get("/sources")
    assert page.status_code == 200
    assert "Sources" in page.text
    assert "Data coming in" in page.text
    assert "Actions going out" in page.text
    assert "MCP" in page.text
    assert "YouTube" in page.text
    assert "kind-card" in page.text
    assert "Web address" in page.text
    assert "Slack" in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
    assert "connect the first system" in page.text


def test_sources_json_endpoints(client: TestClient):
    body = client.post(
        "/sources",
        json={
            "name": "feed",
            "kind": "synthetic",
            "object_type": "Package",
            "config": {"rows": [{"id": "HTTP1", "status": "in_transit"}]},
        },
    )
    assert body.status_code == 200
    assert body.json()["name"] == "feed"
    listed = client.get("/sources.json").json()
    assert any(s["name"] == "feed" for s in listed["sources"])
    pulled = client.post("/sources/feed/pull").json()
    assert pulled["count"] == 1
    # The object is now in the ontology.
    obj = client.get("/objects/Package/HTTP1").json()
    assert obj["properties"]["status"] == "in_transit"


def test_logic_source_http_endpoint(client: TestClient):
    body = client.post(
        "/logic-sources",
        json={"name": "logic", "kind": "http", "config": {"url": "https://example.invalid/x"}},
    )
    assert body.status_code == 200
    assert body.json()["name"] == "logic"


def test_action_target_http_endpoint(client: TestClient):
    body = client.post(
        "/action-targets",
        json={
            "action_type": "mark_delivered",
            "kind": "webhook",
            "config": {"url": "https://example.invalid/hook"},
        },
    )
    assert body.status_code == 200
    assert body.json()["action_type"] == "mark_delivered"
    listed = client.get("/action-targets").json()
    assert any(t["action_type"] == "mark_delivered" for t in listed["targets"])


def test_propose_action_http_endpoint(client: TestClient):
    body = client.post(
        "/ai/propose-action",
        json={
            "action_type": "mark_delivered",
            "parameters": {"package": {"type": "Package", "id": "1Z999"}},
            "confidence": 0.4,
        },
    )
    assert body.status_code == 200
    assert body.json()["hitl"] is True
    assert body.json()["proposal"]["kind"] == "action_application"


def test_contract_endpoint(client: TestClient):
    contract = client.get("/contract").json()
    assert "mcp" in contract
    assert "hermes" in contract
    assert "adk" in contract
    names = {t["name"] for t in contract["mcp"]}
    assert "pull_source" in names
    assert "ingest_source" in names
    assert "propose_action" in names


def test_sdk_page_renders(client: TestClient):
    page = client.get("/sdk")
    assert page.status_code == 200
    assert "SDK" in page.text
    assert "MCP surface" in page.text
    assert "ontology, callable" in page.text
    # The raw contract is available at /contract (and /contract.json for power users).
    assert "/contract" in page.text


def test_sources_page_in_nav(client: TestClient):
    workspace = client.get("/graph").text
    assert "/sources" in workspace
    assert "Sources" in workspace


def test_ingest_webhook_http(client: TestClient):
    client.post(
        "/sources",
        json={
            "name": "inbox",
            "kind": "webhook",
            "object_type": "Package",
            "config": {"token": "abc123", "id_field": "id"},
        },
    )
    denied = client.post("/ingest/inbox", json=[{"id": "IN1", "status": "lost"}])
    assert denied.status_code == 401
    ok = client.post(
        "/ingest/inbox",
        json=[{"id": "IN1", "status": "lost"}],
        headers={"Authorization": "Bearer abc123"},
    )
    assert ok.status_code == 200
    assert ok.json()["count"] == 1
    obj = client.get("/objects/Package/IN1").json()
    assert obj["properties"]["status"] == "lost"


def test_sources_form_creates_http_connection(client: TestClient, monkeypatch):
    page = client.post(
        "/sources/form",
        data={
            "name": "site",
            "kind": "http",
            "object_type": "Package",
            "url": "https://example.invalid/rows",
            "id_field": "id",
        },
        follow_redirects=True,
    )
    assert page.status_code == 200
    assert "site" in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text


def test_add_kind_form_has_no_json(client: TestClient):
    page = client.get("/sources?add=http&layer=data")
    assert page.status_code == 200
    assert "Save connection" in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
    assert "cfg-code" not in page.text
