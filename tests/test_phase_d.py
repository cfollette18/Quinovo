from __future__ import annotations

from quinovo.actions.apply import ActionError
from quinovo.engine.postgres import sqlite_ddl_to_postgres
from quinovo.kernel import open_kernel
import pytest


def test_customer_cannot_mark_neighbors_package_delivered(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "d.sqlite")
    with pytest.raises(ActionError):
        kernel.apply_action(
            "mark_delivered",
            {"package": {"id": "UPS001"}},
            "bob",
        )
    with pytest.raises(PermissionError):
        kernel.get_object("Package", "UPS001", actor="bob")
    visible = kernel.filter_objects("Package", actor="bob")["objects"]
    assert {item["id"] for item in visible} == {"1Z999"}
    bobs = kernel.get_object("Package", "1Z999", actor="bob")
    assert "route_code" not in bobs["properties"]
    warehouse = kernel.get_object("Package", "1Z999")
    assert warehouse["properties"]["route_code"] == "MEM1"


def test_warehouse_dock_cannot_mark_neighbors_package(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "d.sqlite")
    own = kernel.apply_action(
        "mark_delivered",
        {"package": {"id": "1Z999"}},
        "amazon-dock",
    )
    assert own["objects"][0]["properties"]["status"] == "delivered"
    with pytest.raises(ActionError, match="cannot act"):
        kernel.apply_action(
            "mark_delivered",
            {"package": {"id": "UPS001"}},
            "amazon-dock",
        )
    assert kernel.get_object("Package", "UPS001")["properties"]["status"] == "in_transit"


def test_mcp_mark_delivered_is_not_unattended(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "d.sqlite")
    result = kernel.apply_action(
        "mark_delivered",
        {"package": {"id": "1Z999"}},
        "mcp-agent",
        channel="mcp",
    )
    assert result["result"] == "pending_approval"
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "in_transit"
    pending = kernel.store.list_pending_actions()
    assert pending
    approved = kernel.approve_pending_action(pending[0]["id"], "warehouse-agent")
    assert approved["objects"][0]["properties"]["status"] == "delivered"


def test_object_view_and_schema_manager(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "d.sqlite")
    page = kernel.object_view("Package", "1Z999")
    assert "1Z999" in page
    assert "mark_delivered" in page
    assert "Cherry lipstick" in page
    assert "Bob" in page
    assert "Amazon" in page
    manager = kernel.schema_manager()
    assert "Package" in manager
    assert "notify_buyer" in manager


def test_scenario_does_not_touch_production_until_applied(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "d.sqlite")
    kernel.store.scenario_set("memphis", "Package", "1Z999", "status", "rerouted")
    live = kernel.get_object("Package", "1Z999")
    assert live["properties"]["status"] == "in_transit"
    preview = kernel.get_object("Package", "1Z999", scenario="memphis")
    assert preview["properties"]["status"] == "rerouted"
    kernel.store.apply_scenario("memphis")
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "rerouted"


def test_postgres_ddl_is_not_a_lakehouse():
    ddl = "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)"
    converted = sqlite_ddl_to_postgres(ddl)
    assert "IDENTITY" in converted
    assert "AUTOINCREMENT" not in converted
