"""Store schema conventions: migration from v0, cascade delete, action rejection."""

from __future__ import annotations

import sqlite3

import pytest

from conftest import EXAMPLE_PACK
from quinovo.actions.apply import ActionError
from quinovo.engine.store import ObjectStore
from quinovo.kernel import open_kernel
from quinovo.language.load import load_ontology

_OLD_SCHEMA = """
CREATE TABLE objects (
    object_type TEXT NOT NULL,
    pk TEXT NOT NULL,
    properties TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (object_type, pk)
);
CREATE TABLE audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    at TEXT NOT NULL,
    parameters TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE TABLE sources (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    object_type TEXT NOT NULL,
    config TEXT NOT NULL,
    auto_pull INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
"""


def test_v0_database_migrates_to_conventions(tmp_path):
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO objects (object_type, pk, properties, version) "
        "VALUES ('Package', '1Z999', '{\"id\": \"1Z999\", \"status\": \"in_transit\"}', 3)"
    )
    conn.execute(
        "INSERT INTO audit (action_type, actor, at, parameters, result) "
        "VALUES ('mark_delivered', 'warehouse', '2026-01-01T00:00:00Z', '{}', 'applied')"
    )
    conn.commit()
    conn.close()

    ontology = load_ontology(EXAMPLE_PACK / "ontology.yaml")
    store = ObjectStore(ontology, db)

    version = store._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1
    obj = store.get_object("Package", "1Z999")
    assert obj is not None
    assert obj.version == 3
    assert obj.properties["status"] == "in_transit"
    audit = store.list_audit()
    assert audit[0].created_at == "2026-01-01T00:00:00Z"
    source_cols = {row[1] for row in store._conn.execute("PRAGMA table_info(sources)")}
    assert "auto" in source_cols
    assert "auto_pull" not in source_cols
    # brand-new tables from the conventions schema exist after migrate
    names = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"events", "hooks", "forecast_accuracy"} <= names
    store.close()


def test_delete_object_cascades_everything(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "cascade.sqlite")
    store = kernel.store
    kernel.upsert_object("Package", {"id": "CASC1", "status": "in_transit"})
    store.put_forecast("Package", "CASC1", "late_risk", 24, 0.4, "naive", 0.9)
    store.upsert_inferred_fact(
        "Package", "CASC1", "open", "true", 0.9, "test_rule", "inferred", "asserted"
    )
    store.append_series_point("Package", "CASC1", "late_risk", "2026-09-01T00:00:00Z", 0.2)
    store.mark_overlay("Package", "CASC1", ["status"])
    store.scenario_set("scen", "Package", "CASC1", "status", "rerouted")

    kernel.delete_object("Package", "CASC1")

    assert store.get_object("Package", "CASC1") is None
    assert store.list_forecasts("Package", "CASC1") == []
    assert store.list_inferred_facts("Package", "CASC1") == []
    assert store.series_window("Package", "CASC1", "late_risk") == []
    with store._lock:
        overlay = store._conn.execute(
            "SELECT 1 FROM property_overlay WHERE object_type = 'Package' AND object_id = 'CASC1'"
        ).fetchone()
        scenario = store._conn.execute(
            "SELECT 1 FROM scenario_edits WHERE object_type = 'Package' AND object_id = 'CASC1'"
        ).fetchone()
    assert overlay is None
    assert scenario is None


def test_reject_pending_action_closes_it(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "reject.sqlite")
    result = kernel.apply_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        "mcp-agent",
        channel="mcp",
    )
    assert result["result"] == "pending_approval"
    pending = kernel.list_pending_actions()["actions"]
    assert len(pending) == 1

    rejected = kernel.reject_pending_action(pending[0]["id"], "human")
    body = rejected["pending_action"]
    assert body["status"] == "rejected"
    assert body["resolved_by"] == "human"
    assert body["resolved_at"]
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "in_transit"

    with pytest.raises(ActionError):
        kernel.approve_pending_action(pending[0]["id"], "human")
    with pytest.raises(ActionError):
        kernel.reject_pending_action(pending[0]["id"], "human")
    with pytest.raises(KeyError):
        kernel.reject_pending_action(9999, "human")
