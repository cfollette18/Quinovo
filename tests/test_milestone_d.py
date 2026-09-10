from __future__ import annotations

import pytest

from conftest import EXAMPLE_PACK
from quinovo.actions.apply import ActionError
from quinovo.engine.sql import is_postgres_dsn, open_sql_connection, rows_from_query
from quinovo.kernel import open_kernel


def test_customer_cannot_mark_neighbors_package_delivered(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "d.sqlite")
    with pytest.raises(ActionError):
        kernel.apply_action(
            "mark_delivered",
            {"package": {"type": "Package", "id": "UPS001"}},
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
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "d.sqlite")
    own = kernel.apply_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        "amazon-dock",
    )
    assert own["objects"][0]["properties"]["status"] == "delivered"
    with pytest.raises(ActionError, match="cannot act"):
        kernel.apply_action(
            "mark_delivered",
            {"package": {"type": "Package", "id": "UPS001"}},
            "amazon-dock",
        )
    assert kernel.get_object("Package", "UPS001")["properties"]["status"] == "in_transit"


def test_mcp_mark_delivered_is_not_unattended(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "d.sqlite")
    result = kernel.apply_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        "mcp-agent",
        channel="mcp",
    )
    assert result["result"] == "pending_approval"
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "in_transit"
    pending = kernel.store.list_pending_actions()
    assert pending
    approved = kernel.approve_pending_action(pending[0].id, "warehouse-agent")
    assert approved["objects"][0]["properties"]["status"] == "delivered"


def test_object_view_and_schema_manager(client):
    page = client.get("/view/Package/1Z999").text
    assert "1Z999" in page
    assert "mark_delivered" in page
    assert "Cherry lipstick" in page
    assert "Bob" in page
    assert "Amazon" in page
    manager = client.get("/catalog").text
    assert "Package" in manager
    assert "Notify Buyer" in manager
    assert "Kinds of things" in manager


def test_scenario_does_not_touch_production_until_applied(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "d.sqlite")
    kernel.store.scenario_set("memphis", "Package", "1Z999", "status", "rerouted")
    live = kernel.get_object("Package", "1Z999")
    assert live["properties"]["status"] == "in_transit"
    preview = kernel.get_object("Package", "1Z999", scenario="memphis")
    assert preview["properties"]["status"] == "rerouted"
    kernel.store.apply_scenario("memphis")
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "rerouted"


def test_sql_connector_helpers_round_trip_sqlite(tmp_path):
    assert is_postgres_dsn("postgresql://localhost/db")
    assert not is_postgres_dsn(str(tmp_path / "t.sqlite"))
    conn = open_sql_connection(str(tmp_path / "t.sqlite"))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES ('alpha')")
    conn.commit()
    rows = rows_from_query(conn, "SELECT id, name FROM t")
    assert rows == [{"id": 1, "name": "alpha"}]
    conn.close()
