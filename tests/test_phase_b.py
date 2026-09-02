from __future__ import annotations

from quinovo.initpack import init_pack
from quinovo.kernel import open_kernel
from quinovo.language.load import load_ontology
from quinovo.adapters import adk_function_tools, hermes_skill
from quinovo.funnel.tailscale import ingest_tailscale_fixture
from quinovo.paths import CLINIC_PACK, HOMELAB_PACK, ROOT
from quinovo.propose import extract_types


def test_example_implements_trackable():
    ont = load_ontology("packs/example/ontology.yaml")
    pkg = ont.object_type("Package")
    assert "Trackable" in pkg.implements
    assert any(p.api_name == "status" for p in pkg.properties)


def test_homelab_pack_loads_without_live_tailscale(tmp_path):
    kernel = open_kernel(HOMELAB_PACK, tmp_path / "lab.sqlite")
    heater = kernel.get_object("Device", "nheater")
    assert heater["properties"]["hostname"] == "heater"
    assert kernel.search_around("Device", "nheater", "services")["objects"][0]["id"] == "qwen35-server"
    applied = kernel.apply_action(
        "acknowledge_alert",
        {"alert": {"id": "alert-heater-expose"}},
        "local",
    )
    assert applied["objects"][0]["properties"]["status"] == "acked"


def test_homelab_fixture_connector(tmp_path):
    kernel = open_kernel(HOMELAB_PACK, tmp_path / "lab.sqlite")
    count = ingest_tailscale_fixture(
        kernel.store, HOMELAB_PACK / "fixtures" / "tailscale-status.json"
    )
    assert count >= 2
    assert kernel.get_object("Device", "nheater")["properties"]["class"] == "lab"


def test_clinic_pack_honesty_check(tmp_path):
    kernel = open_kernel(CLINIC_PACK, tmp_path / "clinic.sqlite")
    assert kernel.get_object("Patient", "p-1")["properties"]["name"] == "Ada"
    discharged = kernel.apply_action("discharge", {"patient": {"id": "p-1"}}, "local")
    assert discharged["objects"][0]["properties"]["status"] == "discharged"


def test_init_copies_example_not_homelab(tmp_path):
    dest = tmp_path / "shop"
    init_pack(dest, "example")
    text = (dest / "ontology.yaml").read_text()
    assert "Package" in text
    assert "heater" not in text


def test_propose_types_from_markdown_is_hitl(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "notes.md").write_text("# Warehouse\n\n- `city`\n- `capacity`\n")
    kernel = open_kernel(db_path=tmp_path / "p.sqlite")
    proposals = kernel.propose_types(raw, 0.4)
    assert proposals
    assert proposals[0].status == "pending"
    types = {item.api_name for item in kernel.ontology.object_types}
    assert "Warehouse" not in types


def test_hermes_and_adk_share_mcp_tools():
    skill = hermes_skill()
    names = {tool["name"] for tool in skill["tools"]}
    assert "apply_action" in names
    assert "run_inference" in names
    adk = adk_function_tools()
    assert "FunctionTool" in adk
    assert "channel='mcp'" in adk


def test_engine_never_mentions_homelab_nodes():
    blob = ""
    for path in (ROOT / "src" / "quinovo").rglob("*.py"):
        blob += path.read_text(encoding="utf-8")
    assert "heater" not in blob
    assert "nheater" not in blob
    assert "nxtal" not in blob
