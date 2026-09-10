"""Action write-back targets: applying an action drives a real change in an external system."""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel


@pytest.fixture
def kernel(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "tgt.sqlite")


def test_register_action_target(kernel):
    body = kernel.register_action_target(
        "mark_delivered", "webhook", {"url": "https://example.invalid/hook"}, description="erp"
    )
    assert body["action_type"] == "mark_delivered"
    assert body["kind"] == "webhook"
    listed = kernel.list_action_targets()["targets"]
    assert len(listed) == 1


def test_register_target_unknown_action(kernel):
    with pytest.raises(ValueError):
        kernel.register_action_target("not_an_action", "webhook", {"url": "x"})


def test_register_target_unknown_kind(kernel):
    with pytest.raises(ValueError):
        kernel.register_action_target("mark_delivered", "ftp", {"url": "x"})


def test_dispatch_fires_on_apply(kernel, monkeypatch):
    kernel.register_action_target(
        "mark_delivered", "webhook", {"url": "https://example.invalid/hook"}
    )
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("quinovo.actions.dispatch.httpx.post", fake_post)
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    assert captured["url"] == "https://example.invalid/hook"
    assert captured["body"]["action_type"] == "mark_delivered"
    # A write_back audit row records the dispatch.
    rows = kernel.store.list_audit()
    write_backs = [r for r in rows if r.action_type == "write_back"]
    assert write_backs
    assert write_backs[-1].result == "applied"


def test_dispatch_failure_does_not_undo_apply(kernel, monkeypatch):
    kernel.register_action_target(
        "mark_delivered", "webhook", {"url": "https://example.invalid/hook"}
    )

    class FakeResponse:
        status_code = 500
        text = "nope"

        def raise_for_status(self):
            from quinovo.actions.dispatch import DispatchError
            raise DispatchError("bad status")

        def json(self):
            return {}

    def fake_post(url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("quinovo.actions.dispatch.httpx.post", fake_post)
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    # The local apply still succeeded.
    assert result["result"] == "applied"
    rows = kernel.store.list_audit()
    write_backs = [r for r in rows if r.action_type == "write_back"]
    assert write_backs[-1].result == "failed"


def test_dispatch_not_fired_for_pending_action(kernel, monkeypatch):
    # mark_delivered via MCP without guard permission parks as pending_approval.
    # A parked action must NOT fire its write-back target.
    kernel.register_action_target(
        "mark_delivered", "webhook", {"url": "https://example.invalid/hook"}
    )
    fired = []

    def fake_post(url, **kwargs):
        fired.append(1)
        raise AssertionError("should not fire")

    monkeypatch.setattr("quinovo.actions.dispatch.httpx.post", fake_post)
    result = kernel.apply_action(
        "mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="mcp-agent", channel="mcp"
    )
    assert result["result"] == "pending_approval"
    assert fired == []


def test_delete_action_target(kernel):
    kernel.register_action_target("mark_delivered", "webhook", {"url": "x"})
    kernel.delete_action_target("mark_delivered")
    assert kernel.list_action_targets()["targets"] == []


class _Ok:
    status_code = 200
    text = "ok"

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


def test_dispatch_slack(kernel, monkeypatch):
    kernel.register_action_target(
        "mark_delivered", "slack", {"url": "https://hooks.example.invalid/slack"}
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return _Ok()

    monkeypatch.setattr("quinovo.actions.dispatch.httpx.post", fake_post)
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    assert captured["url"] == "https://hooks.example.invalid/slack"
    assert "text" in captured["body"]


def test_dispatch_mcp(kernel, monkeypatch):
    kernel.register_action_target(
        "mark_delivered",
        "mcp",
        {"url": "https://example.invalid/mcp", "tool": "apply_change"},
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return _Ok()

    monkeypatch.setattr("quinovo.actions.dispatch.httpx.post", fake_post)
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    assert captured["body"]["params"]["name"] == "apply_change"


def test_dispatch_email_logs_without_smtp(kernel):
    kernel.register_action_target(
        "mark_delivered", "email", {"to": "ops@example.com"}
    )
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    rows = kernel.store.list_audit()
    write_backs = [r for r in rows if r.action_type == "write_back"]
    assert write_backs[-1].result == "applied"
    assert write_backs[-1].parameters["result"]["mode"] == "logged"


def test_dispatch_sql_gated(kernel, tmp_path):
    db = tmp_path / "out.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE outbound (action_type TEXT)")
    conn.commit()
    conn.close()
    kernel.register_action_target(
        "mark_delivered",
        "sql",
        {
            "dsn": str(db),
            "statement": "INSERT INTO outbound (action_type) VALUES (:action_type)",
            "allow_write": True,
            "allowed_tables": ["outbound"],
        },
    )
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT action_type FROM outbound").fetchall()
    conn.close()
    assert rows == [("mark_delivered",)]


def test_dispatch_sql_rejects_without_allow_write(kernel, tmp_path):
    kernel.register_action_target(
        "mark_delivered",
        "sql",
        {
            "dsn": str(tmp_path / "x.sqlite"),
            "statement": "INSERT INTO outbound (action_type) VALUES (:action_type)",
            "allowed_tables": ["outbound"],
        },
    )
    result = kernel.apply_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, actor="human")
    assert result["result"] == "applied"
    rows = kernel.store.list_audit()
    write_backs = [r for r in rows if r.action_type == "write_back"]
    assert write_backs[-1].result == "failed"
