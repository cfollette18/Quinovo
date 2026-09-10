"""Universal adapters: HTTP, JSON feed, webhook ingest, SQL, MCP."""

from __future__ import annotations

import json
import sqlite3

import pytest

from conftest import EXAMPLE_PACK
from quinovo.engine.sql import postgres_driver_available
from quinovo.kernel import open_kernel


@pytest.fixture
def kernel(tmp_path):
    import shutil

    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "src.sqlite")


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_http_source_pulls_rows(kernel, monkeypatch):
    monkeypatch.setattr(
        "quinovo.connectors.mapping.httpx.get",
        lambda *a, **k: _FakeResponse([{"id": "H1", "status": "lost"}]),
    )
    kernel.register_source(
        "web",
        "http",
        "Package",
        {"url": "https://example.invalid/rows", "id_field": "id"},
    )
    result = kernel.pull_source("web")
    assert result["count"] == 1
    assert kernel.get_object("Package", "H1")["properties"]["status"] == "lost"


def test_json_feed_maps_id_field(kernel, monkeypatch):
    monkeypatch.setattr(
        "quinovo.connectors.mapping.httpx.get",
        lambda *a, **k: _FakeResponse(
            {"items": [{"tracking_id": "J1", "state": "in_transit"}]}
        ),
    )
    kernel.register_source(
        "feed",
        "json",
        "Package",
        {
            "url": "https://example.invalid/feed",
            "rows_path": "items",
            "id_field": "tracking_id",
            "property_map": {"state": "status"},
        },
    )
    result = kernel.pull_source("feed")
    assert result["count"] == 1
    assert kernel.get_object("Package", "J1")["properties"]["status"] == "in_transit"


def test_webhook_ingest_and_token(kernel):
    kernel.register_source(
        "inbox",
        "webhook",
        "Package",
        {"token": "secret-token", "id_field": "id"},
    )
    pulled = kernel.pull_source("inbox")
    assert pulled["count"] == 0
    with pytest.raises(PermissionError):
        kernel.ingest_source("inbox", [{"id": "W1", "status": "lost"}], token="nope")
    body = kernel.ingest_source(
        "inbox", [{"id": "W1", "status": "lost"}], token="secret-token"
    )
    assert body["count"] == 1
    assert kernel.get_object("Package", "W1")["properties"]["status"] == "lost"


def test_sql_sqlite_query(kernel, tmp_path):
    db = tmp_path / "feed.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE packages (id TEXT, status TEXT)")
    conn.execute("INSERT INTO packages VALUES ('S1', 'lost')")
    conn.commit()
    conn.close()
    kernel.register_source(
        "warehouse",
        "sql",
        "Package",
        {"path": str(db), "query": "SELECT id, status FROM packages"},
    )
    result = kernel.pull_source("warehouse")
    assert result["count"] == 1
    assert kernel.get_object("Package", "S1")["properties"]["status"] == "lost"


@pytest.mark.skipif(postgres_driver_available(), reason="postgres driver present")
def test_sql_postgres_without_driver(kernel):
    kernel.register_source(
        "pg",
        "sql",
        "Package",
        {"dsn": "postgresql://example.invalid/db", "query": "select 1"},
    )
    with pytest.raises(ValueError, match="postgres"):
        kernel.pull_source("pg")


def test_mcp_http_tool_call(kernel, monkeypatch):
    def fake_post(url, **kwargs):
        assert url == "https://example.invalid/mcp"
        assert kwargs["json"]["params"]["name"] == "list_packages"
        return _FakeResponse({"result": [{"id": "M1", "status": "in_transit"}]})

    monkeypatch.setattr("quinovo.connectors.mcp_source.httpx.post", fake_post)
    kernel.register_source(
        "remote",
        "mcp",
        "Package",
        {"url": "https://example.invalid/mcp", "tool": "list_packages"},
    )
    result = kernel.pull_source("remote")
    assert result["count"] == 1
    assert kernel.get_object("Package", "M1")["properties"]["status"] == "in_transit"


def test_mcp_stdio_example(kernel, tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import json,sys\n"
        "print(json.dumps({'result': [{'id': 'STD1', 'status': 'lost'}]}))\n",
        encoding="utf-8",
    )
    kernel.register_source(
        "local-mcp",
        "mcp",
        "Package",
        {
            "transport": "stdio",
            "command": ["python3", str(script)],
            "tool": "list",
        },
    )
    result = kernel.pull_source("local-mcp")
    assert result["count"] == 1
    assert kernel.get_object("Package", "STD1")["properties"]["status"] == "lost"


def test_paused_source_skips_auto_pull(kernel):
    kernel.register_source(
        "paused",
        "synthetic",
        "Package",
        {"rows": [{"id": "P1", "status": "lost"}]},
        auto=True,
        enabled=False,
    )
    result = kernel.pull_all_sources()
    assert result["pulled"] == []
    with pytest.raises(ValueError, match="paused"):
        kernel.pull_source("paused")
    kernel.set_source_enabled("paused", True)
    assert kernel.pull_source("paused")["count"] == 1
