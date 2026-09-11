from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import CLINIC_PACK
from quinovo.kernel import open_kernel
from quinovo.llm.settings import LLMSettings


def test_graph_payload_is_pack_objects_and_named_links(client: TestClient):
    graph = client.get("/graph.json").json()
    ids = {node["id"] for node in graph["nodes"]}
    assert "Package:1Z999" in ids
    assert "Person:bob" in ids
    kinds = {edge["type"] for edge in graph["edges"]}
    assert "destined_for" in kinds
    assert "shipped_by" in kinds


def test_chat_is_workspace_home(client: TestClient):
    page = client.get("/chat")
    assert page.status_code == 200
    assert "Ask the graph" in page.text
    assert "chat-composer" in page.text
    assert "chat-thread" in page.text
    assert "New chat" in page.text
    assert 'href="/chat"' in page.text
    assert 'title="Chat"' in page.text
    assert 'title="Settings"' in page.text
    assert 'title="Sources"' in page.text
    assert 'href="/settings"' in page.text
    assert "Twin" not in page.text
    assert 'title="Graph"' not in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
    assert "/assets/chrome.css" in page.text
    css = client.get("/assets/chrome.css")
    assert css.status_code == 200
    assert "#ff3621" in css.text
    assert ".chat-shell" in css.text
    assert ".chat-step" in css.text
    assert "chat-step" in page.text
    catalog = client.get("/catalog")
    assert catalog.status_code == 200
    assert "Catalog" in catalog.text
    assert "json-panel" not in catalog.text
    assert "<pre" not in catalog.text
    logic = client.get("/inference")
    assert logic.status_code == 200
    assert "Needs a look" in logic.text
    history = client.get("/audit")
    assert history.status_code == 200
    assert "Audit" in history.text


def test_landing_page_is_public(client: TestClient):
    page = client.get("/")
    assert page.status_code == 200
    text = page.text
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
    assert "https://github.com/cfollette18/Quinovo" in text
    assert "uv run quinovo serve" in text
    assert "uv run quinovo mcp" in text
    assert "Cursor" in text
    assert "Claude Desktop" in text
    assert "Hermes" in text
    assert "/assets/agents/cursor.svg" in text
    assert "/assets/agents/claude.svg" in text
    assert "/assets/agents/hermes.svg" in text
    assert "Actions write back to the tools you already run" in text
    assert "universal adapters" in text
    assert "SAP" in text
    assert "Salesforce" in text
    assert "Jira" in text
    assert "Slack" in text
    assert "/assets/actions/sap.svg" in text
    assert "/assets/landing.css" in text
    assert "Search by name" not in text
    assert 'href="/chat"' in text
    assert "Apache-2.0" in text
    assert "cfollette18" in text
    assert "hero-visual" in text
    assert "mock-workspace" in text
    assert "mock-chat" in text
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
        "/workspace": "/chat",
        "/twin": "/chat",
        "/graph": "/chat",
        "/manager": "/catalog",
        "/logic": "/inference",
        "/history": "/audit",
    }
    for old, new in moved.items():
        response = client.get(old, follow_redirects=False)
        assert response.status_code == 301, old
        assert response.headers["location"].startswith(new), old
    graph = client.get("/graph.json").json()
    assert "nodes" in graph


def test_clinic_graph_uses_clinic_nouns(tmp_path):
    kernel = open_kernel(CLINIC_PACK, tmp_path / "clinic.sqlite")
    graph = kernel.graph()
    ids = {node["id"] for node in graph["nodes"]}
    assert "Patient:p-1" in ids
    assert "Package:1Z999" not in ids


def test_chat_stream_shows_tool_work(client: TestClient, monkeypatch):
    def fake_turn(kernel, text, *, history=None, settings=None):
        yield {
            "type": "tool",
            "id": "t1",
            "name": "get_object",
            "label": "Read Package 1Z999",
            "calling": "Calling Read",
            "verb": "Read",
            "target": "Package 1Z999",
            "icon": "read",
            "status": "running",
        }
        yield {
            "type": "tool",
            "id": "t1",
            "name": "get_object",
            "label": "Read Package 1Z999",
            "calling": "Calling Read",
            "verb": "Read",
            "target": "Package 1Z999",
            "icon": "read",
            "summary": "Read Package 1Z999",
            "status": "done",
        }
        yield {"type": "text", "text": "Destined for Bob."}
        yield {"type": "done", "text": "Destined for Bob.", "tools": []}

    monkeypatch.setattr("quinovo.chat.agent.run_chat_turn", fake_turn)
    monkeypatch.setattr(
        "quinovo.chat.agent.ensure_settings",
        lambda: LLMSettings(api_key="k", enabled=True, model="MiniMax-M3"),
    )
    with client.stream("POST", "/chat/stream", json={"text": "Where is 1Z999?"}) as res:
        assert res.status_code == 200
        body = "".join(res.iter_text())
    assert "Calling Read" in body
    assert "Read Package 1Z999" in body
    assert "Destined for Bob." in body
    sessions = client.get("/chat/sessions").json()
    assert sessions["sessions"]
    sid = sessions["sessions"][0]["id"]
    saved = client.get(f"/chat/sessions/{sid}").json()
    assert saved["messages"][0]["role"] == "user"
    assert saved["messages"][-1]["text"] == "Destined for Bob."


def test_chat_without_model_explains_settings(client: TestClient):
    from quinovo.llm.settings import LLMSettings, save_settings

    save_settings(LLMSettings(api_key="", enabled=False, model="MiniMax-M3"))
    with client.stream("POST", "/chat/stream", json={"text": "hello"}) as res:
        body = "".join(res.iter_text())
    assert "Settings" in body
