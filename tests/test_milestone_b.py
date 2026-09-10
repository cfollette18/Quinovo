from __future__ import annotations

from conftest import CLINIC_PACK, EXAMPLE_PACK
from quinovo.kernel import open_kernel
from quinovo.language.load import load_ontology
from quinovo.mcp.contract import adk_function_tools, hermes_skill
from quinovo.pack.init import init_pack
from quinovo.workspace import ROOT


def test_example_implements_trackable():
    ont = load_ontology(EXAMPLE_PACK / "ontology.yaml")
    pkg = ont.object_type("Package")
    assert "Trackable" in pkg.implements
    assert any(p.api_name == "status" for p in pkg.properties)


def test_clinic_pack_honesty_check(tmp_path):
    kernel = open_kernel(CLINIC_PACK, tmp_path / "clinic.sqlite")
    assert kernel.get_object("Patient", "p-1")["properties"]["name"] == "Ada"
    discharged = kernel.apply_action("discharge", {"patient": {"type": "Patient", "id": "p-1"}}, "local")
    assert discharged["objects"][0]["properties"]["status"] == "discharged"


def test_init_copies_world_starter(tmp_path):
    dest = tmp_path / "shop"
    init_pack(dest, "world")
    text = (dest / "ontology.yaml").read_text()
    assert "Topic" in text
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


def test_engine_source_has_no_lab_hostnames():
    blob = ""
    for path in (ROOT / "src" / "quinovo").rglob("*.py"):
        blob += path.read_text(encoding="utf-8")
    assert "heater" not in blob
    assert "nheater" not in blob
    assert "nxtal" not in blob
