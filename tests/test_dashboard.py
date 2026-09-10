from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import CLINIC_PACK
from quinovo.kernel import open_kernel


def test_graph_is_pack_objects_and_named_links(client: TestClient):
    graph = client.get("/graph.json").json()
    ids = {node["id"] for node in graph["nodes"]}
    assert "Package:1Z999" in ids
    assert "Person:bob" in ids
    kinds = {edge["type"] for edge in graph["edges"]}
    assert "destined_for" in kinds
    assert "shipped_by" in kinds


def test_dashboard_page_is_queryable(client: TestClient):
    page = client.get("/graph")
    assert page.status_code == 200
    assert "Extend graph" in page.text
    assert "/graph" in page.text
    assert "Search by name" in page.text
    assert "Package 1Z999" not in page.text
    assert 'href="/settings"' in page.text
    assert 'title="Settings"' in page.text
    assert 'href="/twin"' in page.text
    assert 'title="Twin"' in page.text
    assert 'title="Sources"' in page.text
    assert "All kinds" in page.text
    assert "Show all" in page.text
    assert "All connections" in page.text
    assert "All topics" in page.text
    assert 'id="card-modal"' in page.text
    assert "topic-cluster" in page.text
    assert "Click a card to read it" in page.text
    assert "Tick" not in page.text
    assert "Run inference" not in page.text
    assert "page-head" in page.text
    assert 'class="tabs"' in page.text
    assert "/assets/chrome.css" in page.text
    assert "--lava" not in page.text
    css = client.get("/assets/chrome.css")
    assert css.status_code == 200
    assert "#ff3621" in css.text
    assert "margin-top: auto" not in css.text
    assert ".card-modal" in css.text
    assert ".topic-cluster" in css.text
    catalog = client.get("/catalog")
    assert catalog.status_code == 200
    assert "Catalog" in catalog.text
    assert "Kinds of things" in catalog.text
    assert "Actions" in catalog.text
    assert "json-panel" not in catalog.text
    assert "<pre" not in catalog.text
    organized = client.post("/catalog/organize", data={"actor": "human"}, follow_redirects=False)
    assert organized.status_code == 303
    assert organized.headers["location"].startswith("/catalog")
    logic = client.get("/inference")
    assert logic.status_code == 200
    assert "Needs a look" in logic.text
    assert "Run inference" not in logic.text
    assert ">Tick<" not in logic.text
    assert "language model from Settings" in logic.text
    assert "/inference.json" in logic.text
    history = client.get("/audit")
    assert history.status_code == 200
    assert "Audit" in history.text


def test_landing_page_is_public(client: TestClient):
    page = client.get("/")
    assert page.status_code == 200
    text = page.text
    # The twist: six differentiators stated in plain language.
    assert "Discovered, not hand-built" in text
    assert "MCP is the connector layer" in text
    assert "Small specialists, not one giant model" in text
    assert "HITL is the only human job" in text
    assert "The ontology is the record" in text
    assert "Security is a primitive" in text
    assert "Open source" not in text
    assert text.count('class="why-card') == 6
    assert "why-discovered" in text
    assert "why-record" in text
    # Public calls to action: GitHub, run locally, connect an agent.
    assert "https://github.com/cfollette18/Quinovo" in text
    assert "uv run quinovo serve" in text
    assert "uv run quinovo mcp" in text
    # MCP config blocks for the three named clients.
    assert "Cursor" in text
    assert "Claude Desktop" in text
    assert "Hermes" in text
    assert "/assets/agents/cursor.svg" in text
    assert "/assets/agents/claude.svg" in text
    assert "/assets/agents/hermes.svg" in text
    # Action layer: write-backs to systems teams already run.
    assert "Actions write back to the tools you already run" in text
    assert "universal adapters" in text
    assert "SAP" in text
    assert "Salesforce" in text
    assert "Jira" in text
    assert "Slack" in text
    assert "/assets/actions/sap.svg" in text
    # The landing page is its own thing — no workspace chrome.
    assert "/assets/landing.css" in text
    assert "Search by name" not in text
    # Workspace graph still reachable at /graph from the landing nav.
    assert 'href="/twin"' in text
    # Apache-2.0 attribution in the footer.
    assert "Apache-2.0" in text
    assert "cfollette18" in text
    # Databricks-style graphics: workspace mockup + architecture diagram.
    assert "hero-visual" in text
    assert "mock-workspace" in text
    assert "arch-diagram" in text
    assert "loop-rail" not in text
    assert "json-panel" not in text
    assert "<pre" not in text
    css = client.get("/assets/landing.css")
    assert css.status_code == 200
    assert "@keyframes why-fade-in" in css.text
    assert "@keyframes why-lock" in css.text
    assert "prefers-reduced-motion: reduce" in css.text


def test_old_workspace_routes_redirect(client: TestClient):
    moved = {
        "/workspace": "/graph",
        "/manager": "/catalog",
        "/logic": "/inference",
        "/history": "/audit",
    }
    for old, new in moved.items():
        response = client.get(old, follow_redirects=False)
        assert response.status_code == 301, old
        assert response.headers["location"].startswith(new), old
    twin = client.get("/twin")
    assert twin.status_code == 200
    assert "Twin" in twin.text
    graph = client.get("/graph.json").json()
    assert "nodes" in graph


def test_clinic_graph_uses_clinic_nouns(tmp_path):
    kernel = open_kernel(CLINIC_PACK, tmp_path / "clinic.sqlite")
    graph = kernel.graph()
    ids = {node["id"] for node in graph["nodes"]}
    assert "Patient:p-1" in ids
    assert "Package:1Z999" not in ids
