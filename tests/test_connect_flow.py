"""Tests for the local sign-in → guided connect flow on the landing page.

Covers:
- the "Connect your agent" button is present on `/` when signed out,
- the local sign-in flow (first visit sets a passphrase, later visits require it),
- `/connect` renders after sign-in and contains the real `uv run quinovo mcp`
  snippet with absolute paths filled in,
- no API keys are leaked into the rendered pages,
- sign-out clears the session and re-gates `/connect`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_landing_has_connect_button_when_signed_out(client: TestClient):
    page = client.get("/")
    assert page.status_code == 200
    text = page.text
    # The friendly button is present and points at the sign-in gate.
    assert "Connect your agent" in text
    assert 'href="/signin?next=/connect"' in text
    # Agent logo cards are shown instead of raw JSON blocks.
    assert "agent-card" in text
    assert "Cursor" in text
    assert "Claude Desktop" in text
    assert "Hermes" in text
    assert "/assets/agents/cursor.svg" in text
    # No raw JSON anywhere on the landing page.
    assert "json-panel" not in text
    assert "Show the raw copy-paste config" not in text
    assert "<pre" not in text
    assert "hero-visual" in text


def test_connect_redirects_to_signin_when_signed_out(client: TestClient):
    resp = client.get("/connect", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signin?next=/connect"


def test_signin_page_renders_first_visit(client: TestClient):
    page = client.get("/signin")
    assert page.status_code == 200
    # First visit: the form asks to *claim* the instance.
    assert "Claim this Quinovo" in page.text
    assert "Set a passphrase" in page.text
    assert "Local sign-in" in page.text
    # Honest copy: no OAuth claim.
    assert "no OAuth" in page.text


def test_first_visit_signin_sets_passphrase_and_redirects_to_connect(
    client: TestClient, tmp_path,
):
    resp = client.post(
        "/signin",
        data={"passphrase": "local-only", "next": "/connect"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect"
    # A session cookie was issued.
    assert "quinovo_session" in resp.cookies
    # Following the redirect now renders the connect page (session carried).
    page = client.get("/connect")
    assert page.status_code == 200
    assert "Point your agent at Quinovo" in page.text


def test_connect_page_contains_real_mcp_snippet_with_absolute_paths(
    client: TestClient,
):
    # Sign in (first visit claims the instance).
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    page = client.get("/connect")
    assert page.status_code == 200
    text = page.text
    # The snippet uses the canonical command.
    assert "uv run quinovo mcp" in text
    # Absolute pack/db paths are filled in from this install (not placeholders).
    assert "/abs/path/to/your/pack" not in text
    assert "/abs/path/to/quinovo.sqlite" not in text
    # Per-agent sections exist.
    assert "Cursor" in text
    assert "Claude Desktop" in text
    assert "Hermes" in text
    assert "Other (any MCP client)" in text
    assert "/assets/agents/cursor.svg" in text
    assert "/assets/agents/mcp.svg" in text
    # Copy + test buttons exist.
    assert "Copy config" in text
    assert "Test connection" in text
    # No raw JSON anywhere on the connect page — agent logo cards instead.
    assert "json-panel" not in text
    assert "agent-card" in text
    # The /connect/config endpoint returns the full config as plain text.
    cfg = client.get("/connect/config/cursor")
    assert cfg.status_code == 200
    assert "mcpServers" in cfg.text
    assert "quinovo" in cfg.text


def test_connect_test_endpoint_requires_session(client: TestClient):
    resp = client.post("/connect/test")
    assert resp.status_code == 401


def test_connect_test_endpoint_reports_reachable_when_signed_in(client: TestClient):
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    resp = client.post("/connect/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "reachable"
    assert "ontology" in body


def test_second_visit_requires_passphrase(client: TestClient):
    # First visit claims the instance.
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    # Sign out.
    client.post("/signout")
    # The signin page now shows the returning-visitor copy, not the claim copy.
    page = client.get("/signin")
    assert "Sign in to Quinovo" in page.text
    assert "Claim this Quinovo" not in page.text
    # Wrong passphrase is rejected.
    bad = client.post(
        "/signin",
        data={"passphrase": "wrong", "next": "/connect"},
        follow_redirects=False,
    )
    assert bad.status_code == 401
    assert "match this Quinovo instance" in bad.text
    # Correct passphrase works.
    good = client.post(
        "/signin",
        data={"passphrase": "local-only", "next": "/connect"},
        follow_redirects=False,
    )
    assert good.status_code == 303
    assert good.headers["location"] == "/connect"


def test_signout_clears_session_and_re_gates_connect(client: TestClient):
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    assert client.get("/connect").status_code == 200
    resp = client.post("/signout", follow_redirects=False)
    assert resp.status_code == 303
    # After signout, /connect is gated again.
    gated = client.get("/connect", follow_redirects=False)
    assert gated.status_code == 303
    assert gated.headers["location"] == "/signin?next=/connect"


def test_landing_button_reflects_signed_in_state(client: TestClient):
    # Signed out: button label is "Connect your agent" → signin gate.
    out = client.get("/").text
    assert ">Connect your agent</a>" in out
    assert 'btn-connect" href="/signin?next=/connect"' in out
    assert ">Manage connection</a>" not in out
    # Signed in: button becomes "Manage connection" → /connect directly.
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    inn = client.get("/").text
    assert ">Manage connection</a>" in inn
    assert 'btn-connect" href="/connect"' in inn
    assert ">Connect your agent</a>" not in inn


def test_no_api_keys_leaked_in_pages(client: TestClient):
    client.post("/signin", data={"passphrase": "local-only", "next": "/connect"})
    # A fake-looking key should never appear in any rendered page.
    fake_key = "sk-abcdef1234567890secretkey"
    for path in ("/", "/signin", "/connect"):
        page = client.get(path)
        assert fake_key not in page.text
        assert "sk-" not in page.text
    # The connect-test endpoint must not echo any actual key value or tail.
    body = client.post("/connect/test").json()
    rendered = str(body)
    assert "sk-" not in rendered
    # No key-tail / key-set metadata fields are exposed by the connect flow.
    assert "api_key_tail" not in rendered
    assert "api_key_set" not in rendered


def test_landing_renders_with_empty_kernel(client: TestClient):
    # The landing page must still render even when the kernel has no objects.
    page = client.get("/")
    assert page.status_code == 200
    assert "Discovered, not hand-built" in page.text
