from __future__ import annotations

import json
import shutil
import time

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel
from quinovo.language.load import load_ontology
from quinovo.llm.author import AUTHORING_COOLDOWN
from quinovo.llm.engine import LLMEngine
from quinovo.llm.settings import LLMSettings, save_settings
from quinovo.loop.runner import start_autonomy
from quinovo.workspace import resolve_serve_paths

NEW_RULE = {
    "api_name": "synth_test_late",
    "kind": "property_fact",
    "description": "test rule",
    "source_type": "Package",
    "confidence": 0.9,
    "when_property": {"api_name": "status", "equals": "lost"},
    "then_fact": {"predicate": "lost", "value": "true"},
}

PACK_SPEC = {
    "ontology": {
        "ontology": {"api_name": "autoworld", "display_name": "Auto", "description": "synth"},
        "object_types": [
            {
                "api_name": "Item",
                "primary_key": "id",
                "title_property": "id",
                "properties": [{"api_name": "id", "type": "string"}],
            }
        ],
    }
}


def _copied(tmp_path):
    dest = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, dest)
    return open_kernel(dest, tmp_path / "db.sqlite"), dest


def test_tick_does_not_rewrite_teaching_pack(tmp_path):
    kernel, dest = _copied(tmp_path)
    text = (dest / "inference.yaml").read_text(encoding="utf-8")
    result = kernel.tick()
    assert (dest / "inference.yaml").read_text(encoding="utf-8") == text
    assert result["pending_proposals"] == []
    assert "pending_proposals" in result


def test_tick_synthesizes_rules_as_hitl_when_pack_has_none(tmp_path):
    kernel, dest = _copied(tmp_path)
    (dest / "inference.yaml").unlink()
    kernel.reload()
    result = kernel.tick()
    assert result["pending_proposals"]
    assert all(item["status"] == "pending" for item in result["pending_proposals"])
    assert all(item["kind"] == "inference_rule" for item in result["pending_proposals"])
    assert not (dest / "inference.yaml").exists()


def test_rule_below_80_is_hitl_until_human_approves(tmp_path):
    kernel, dest = _copied(tmp_path)
    body = kernel.propose("inference_rule", NEW_RULE, 0.55)
    assert body["hitl"] is True
    text = (dest / "inference.yaml").read_text(encoding="utf-8")
    assert "synth_test_late" not in text

    approved = kernel.approve_proposal(body["proposal"]["id"], "human")
    assert approved["proposal"]["status"] == "approved"
    written = (dest / "inference.yaml").read_text(encoding="utf-8")
    assert "synth_test_late" in written
    names = {rule.api_name for rule in kernel.ruleset.rules}
    assert "synth_test_late" in names


def test_rule_at_90_auto_writes_yaml(tmp_path):
    kernel, dest = _copied(tmp_path)
    body = kernel.propose("inference_rule", NEW_RULE, 0.9)
    assert body["hitl"] is False
    assert body["proposal"]["status"] == "auto_applied"
    assert "synth_test_late" in (dest / "inference.yaml").read_text(encoding="utf-8")


def test_rejected_rule_is_not_reproposed_on_tick(tmp_path):
    kernel, dest = _copied(tmp_path)
    body = kernel.propose("inference_rule", NEW_RULE, 0.4)
    kernel.reject_proposal(body["proposal"]["id"], "human")
    kernel.tick()
    pending_names = {
        item.payload["api_name"]
        for item in kernel.store.list_proposals("pending")
        if item.kind == "inference_rule"
    }
    assert "synth_test_late" not in pending_names
    assert "synth_test_late" not in (dest / "inference.yaml").read_text(encoding="utf-8")


def test_propose_pack_is_hitl_until_approved(tmp_path):
    kernel, _dest = _copied(tmp_path)
    new_pack = tmp_path / "autoworld"
    body = kernel.propose("pack", {"dest": str(new_pack), "spec": PACK_SPEC}, 0.5)
    assert body["hitl"] is True
    assert not new_pack.exists()
    kernel.approve_proposal(body["proposal"]["id"], "human")
    assert (new_pack / "ontology.yaml").exists()
    ont = load_ontology(new_pack / "ontology.yaml")
    assert ont.ontology.api_name == "autoworld"


def test_propose_pack_high_confidence_writes(tmp_path):
    kernel, _dest = _copied(tmp_path)
    new_pack = tmp_path / "autoworld"
    body = kernel.propose("pack", {"dest": str(new_pack), "spec": PACK_SPEC}, 0.9)
    assert body["hitl"] is False
    assert (new_pack / "ontology.yaml").exists()


def test_type_proposal_persists_to_ontology_yaml(tmp_path):
    kernel, dest = _copied(tmp_path)
    body = kernel.propose(
        "type_definition",
        {
            "api_name": "Return",
            "primary_key": "id",
            "title_property": "id",
            "properties": [
                {"api_name": "id", "type": "string"},
                {"api_name": "reason", "type": "string"},
            ],
        },
        0.86,
    )
    assert body["hitl"] is False
    ont = load_ontology(dest / "ontology.yaml")
    assert ont.object_type("Return").api_name == "Return"
    types = {item.api_name for item in kernel.ontology.object_types}
    assert "Return" in types


def test_create_app_starts_autonomy_and_reload_keeps_it(client):
    kernel = client.app.state.kernel
    loop = kernel._autonomy
    assert loop is not None
    assert loop._thread.is_alive()
    thread = loop._thread
    kernel.reload()
    assert kernel._autonomy is loop
    assert kernel._autonomy._thread is thread
    assert thread.is_alive()


def test_workspace_html_has_no_tick_or_run_inference(client):
    forbidden = (
        "Run inference",
        ">Tick<",
        'id="tick"',
        'id="run-inference"',
        'fetch("/tick")',
        "fetch('/tick')",
        'fetch("/inference/run")',
        "fetch('/inference/run')",
    )
    for path in ("/", "/inference", "/catalog", "/audit", "/settings"):
        text = client.get(path).text
        for needle in forbidden:
            assert needle not in text, f"{needle!r} found on {path}"
    assert "language model from Settings" in client.get("/inference").text
    queue = client.get("/inference.json")
    assert queue.status_code == 200
    assert "proposals" in queue.json()


def test_upsert_and_remove_link_nudge(tmp_path):
    kernel, _dest = _copied(tmp_path)
    start_autonomy(kernel, interval=60)
    kernel._autonomy._wake.clear()
    kernel.upsert_object("Package", {"id": "NUDGE1", "status": "lost"})
    assert kernel._autonomy._wake.is_set()
    kernel._autonomy._wake.clear()
    kernel.set_link("destined_for", "NUDGE1", "bob")
    assert kernel._autonomy._wake.is_set()
    kernel._autonomy._wake.clear()
    kernel.remove_link("destined_for", "NUDGE1", "bob")
    assert kernel._autonomy._wake.is_set()
    kernel._autonomy.stop()


def test_tick_uses_mocked_llm_when_ready(tmp_path, monkeypatch):
    kernel, dest = _copied(tmp_path)
    (dest / "inference.yaml").unlink()
    kernel.reload()
    save_settings(
        LLMSettings(
            provider="minimax",
            model="MiniMax-M3",
            base_url="https://api.minimax.io/anthropic",
            api_key="secret-test-key",
            protocol="anthropic",
        )
    )
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "proposals": [
                                    {
                                        "kind": "inference_rule",
                                        "confidence": 0.55,
                                        "payload": {
                                            "api_name": "llm_status_lost",
                                            "kind": "property_fact",
                                            "description": "LLM noticed lost packages.",
                                            "source_type": "Package",
                                            "confidence": 0.9,
                                            "when_property": {
                                                "api_name": "status",
                                                "equals": "lost",
                                            },
                                            "then_fact": {
                                                "predicate": "lost",
                                                "value": "true",
                                            },
                                        },
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", fake_post)
    first = kernel.tick()
    assert first["authoring"] == "llm"
    names = {
        item["payload"].get("api_name")
        for item in first["proposed"]
        if item.get("payload")
    }
    assert "llm_status_lost" in names
    prompt = captured["json"]["messages"][0]["content"]
    assert "secret-test-key" not in prompt
    second = kernel.tick()
    assert second["authoring"] == "skipped"
    assert second["proposed"] == []


def test_empty_tick_does_not_call_llm(tmp_path, monkeypatch):
    kernel, _dest = _copied(tmp_path)
    save_settings(LLMSettings(api_key="k", model="MiniMax-M3", protocol="anthropic"))
    posts: list[int] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": '{"proposals":[]}'}]}

    def fake_post(url, **kwargs):
        posts.append(1)
        return FakeResponse()

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", fake_post)
    kernel.tick()
    kernel.tick()
    kernel.tick()
    assert len(posts) == 1


def test_wait_for_quiet_coalesces_llm_pass(tmp_path, monkeypatch):
    kernel, dest = _copied(tmp_path)
    (dest / "inference.yaml").unlink()
    kernel.reload()
    save_settings(LLMSettings(api_key="k", model="MiniMax-M3", protocol="anthropic"))
    posts: list[int] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": '{"proposals":[]}'}]}

    def fake_post(url, **kwargs):
        posts.append(1)
        return FakeResponse()

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", fake_post)
    skipped = kernel.tick(wait_for_quiet=True)
    assert skipped["authoring"] == "skipped"
    assert posts == []
    kernel._authoring.changed_at = time.monotonic() - AUTHORING_COOLDOWN - 0.1
    ran = kernel.tick(wait_for_quiet=True)
    assert ran["authoring"] == "llm"
    assert len(posts) == 1


def test_tick_falls_back_to_heuristics_without_key(tmp_path):
    kernel, dest = _copied(tmp_path)
    (dest / "inference.yaml").unlink()
    kernel.reload()
    result = kernel.tick()
    assert result["authoring"] == "heuristic"
    assert result["pending_proposals"]
    assert all(item["kind"] == "inference_rule" for item in result["pending_proposals"])


def test_serve_defaults_to_empty_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("quinovo.workspace.WORKSPACE_ROOT", tmp_path / "ws")
    monkeypatch.setattr("quinovo.workspace.WORKSPACE_PACK", tmp_path / "ws" / "pack")
    monkeypatch.setattr("quinovo.workspace.WORKSPACE_DB", tmp_path / "ws" / "quinovo.sqlite")
    pack, db = resolve_serve_paths()
    assert pack == tmp_path / "ws" / "pack"
    assert db == tmp_path / "ws" / "quinovo.sqlite"
    assert (pack / "ontology.yaml").exists()
    kernel = open_kernel(db_path=tmp_path / "world.sqlite")
    assert kernel.ontology.ontology.api_name == "world"


def test_llm_engine_still_mocked(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "ok"}]}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", fake_post)
    engine = LLMEngine(
        LLMSettings(
            api_key="k",
            model="MiniMax-M3",
            protocol="anthropic",
            base_url="https://api.minimax.io/anthropic",
        )
    )
    assert engine.complete("hi") == "ok"
    assert "k" not in captured["json"]["messages"][0]["content"]
