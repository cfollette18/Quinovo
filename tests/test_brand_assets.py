from __future__ import annotations

from fastapi.testclient import TestClient


def test_logo_svg_is_served_and_valid(client: TestClient):
    r = client.get("/assets/logo.svg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/svg+xml"
    body = r.text
    assert body.lstrip().startswith("<?xml") or body.lstrip().startswith("<svg")
    assert "<svg" in body
    assert "</svg>" in body
    # Brand colors present in the canonical mark.
    assert "#1B3139" in body  # navy
    assert "#FF3621" in body   # lava red focal node


def test_all_brand_assets_are_served(client: TestClient):
    for path, ctype in [
        ("/assets/logo-mark.svg", "image/svg+xml"),
        ("/assets/logo-dark.svg", "image/svg+xml"),
        ("/assets/logo-full.svg", "image/svg+xml"),
        ("/assets/favicon.svg", "image/svg+xml"),
        ("/assets/favicon-32.png", "image/png"),
        ("/assets/logo.png", "image/png"),
        ("/assets/apple-touch-icon.png", "image/png"),
    ]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        assert r.headers["content-type"] == ctype, (path, r.headers["content-type"])


def test_agent_and_action_logos_are_served(client: TestClient):
    for path in (
        "/assets/agents/cursor.svg",
        "/assets/agents/claude.svg",
        "/assets/agents/hermes.svg",
        "/assets/agents/mcp.svg",
        "/assets/actions/sap.svg",
        "/assets/actions/salesforce.svg",
        "/assets/actions/jira.svg",
        "/assets/actions/slack.svg",
        "/assets/actions/mcp.svg",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["content-type"] == "image/svg+xml"
        assert r.text.lstrip().startswith("<svg")
        assert "</svg>" in r.text
    missing = client.get("/assets/agents/not-a-logo.svg")
    assert missing.status_code == 404


def test_landing_page_references_favicon(client: TestClient):
    html = client.get("/").text
    assert 'rel="icon" href="/assets/favicon.svg"' in html
    assert 'rel="apple-touch-icon" href="/assets/apple-touch-icon.png"' in html
    # The landing header still carries the mark + wordmark.
    assert "quinovo" in html


def test_chrome_references_favicon_and_mark(client: TestClient):
    html = client.get("/graph").text
    assert 'rel="icon" href="/assets/favicon.svg"' in html
    # The new knot-Q mark is inlined in the rail (red focal node).
    assert "#FF3621" in html
    assert "#1B3139" in html
