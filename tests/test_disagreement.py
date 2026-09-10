from __future__ import annotations

import shutil
from contextlib import contextmanager

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel
from quinovo.llm import disagreement as disagreement_mod
from quinovo.llm.disagreement import (
    DEFAULT_DISAGREEMENT_DATASET,
    SCORE_NAME,
    ensure_disagreement_dataset,
    record_user_disagreement,
)
from quinovo.llm.tracing import remember_source_trace


class FakeSpan:
    def __init__(self):
        self.updates: list[dict] = []

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, recorded: dict):
        self.recorded = recorded

    def get_dataset(self, name: str, fetch_items_page_size: int = 50):
        if self.recorded.get("dataset_exists"):
            return {"name": name}
        raise LookupError("missing dataset")

    def create_dataset(self, **kwargs):
        self.recorded["datasets"].append(kwargs)
        return {"name": kwargs.get("name")}

    def create_dataset_item(self, **kwargs):
        self.recorded["items"].append(kwargs)
        return kwargs

    def create_score(self, **kwargs):
        self.recorded["scores"].append(kwargs)

    def start_as_current_observation(self, **kwargs):
        self.recorded["spans"].append(kwargs)
        return FakeSpan()

    def get_current_trace_id(self):
        return "trace-disagreement"

    def get_current_observation_id(self):
        return "obs-disagreement"

    def flush(self):
        self.recorded["flushed"] = True


@pytest.fixture
def langfuse(monkeypatch):
    disagreement_mod._DATASET_READY = False
    recorded: dict = {
        "datasets": [],
        "items": [],
        "scores": [],
        "spans": [],
        "dataset_exists": False,
        "flushed": False,
    }
    client = FakeClient(recorded)

    @contextmanager
    def fake_propagate(**kwargs):
        recorded["attrs"] = kwargs
        yield

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    monkeypatch.setattr("quinovo.llm.tracing._client", lambda: client)
    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate, raising=False)
    return recorded


def test_ensure_creates_dataset_once(langfuse):
    assert ensure_disagreement_dataset() is True
    assert ensure_disagreement_dataset() is True
    assert len(langfuse["datasets"]) == 1
    created = langfuse["datasets"][0]
    assert created["name"] == DEFAULT_DISAGREEMENT_DATASET
    assert created["input_schema"]["required"] == ["source", "kind"]
    assert created["expected_output_schema"]["required"] == [
        "disagreement",
        "decision",
        "should_propose",
    ]


def test_false_disagreement_is_not_saved(langfuse):
    record_user_disagreement(
        disagreement=False,
        source="proposal",
        source_id=1,
        actor="human",
        kind="inference_rule",
    )
    assert langfuse["items"] == []
    assert langfuse["scores"] == []


def test_true_disagreement_saves_training_item_and_score(langfuse):
    remember_source_trace("proposal", 9, "trace-origin")
    record_user_disagreement(
        disagreement=True,
        source="proposal",
        source_id=9,
        actor="human",
        kind="inference_rule",
        title="Synth Test Late",
        why="Packages keep going missing.",
        what="A rule that flags lost packages.",
        confidence=0.4,
        payload={"api_name": "synth_test_late", "api_key": "sk-secret"},
    )
    assert len(langfuse["items"]) == 1
    item = langfuse["items"][0]
    assert item["dataset_name"] == DEFAULT_DISAGREEMENT_DATASET
    assert item["id"] == "quinovo-proposal-9"
    assert item["input"]["kind"] == "inference_rule"
    assert item["input"]["payload"]["api_name"] == "synth_test_late"
    assert "api_key" not in item["input"]["payload"]
    assert item["expected_output"] == {
        "disagreement": True,
        "decision": "reject",
        "should_propose": False,
    }
    assert item["source_trace_id"] == "trace-origin"
    assert langfuse["scores"]
    assert langfuse["scores"][0]["name"] == SCORE_NAME
    assert langfuse["scores"][0]["value"] == 1
    assert langfuse["scores"][0]["data_type"] == "BOOLEAN"
    assert langfuse["flushed"] is True


def test_reject_proposal_records_disagreement(tmp_path, monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(
        "quinovo.kernel.record_user_disagreement",
        lambda **kwargs: recorded.append(kwargs),
    )
    dest = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, dest)
    kernel = open_kernel(dest, tmp_path / "db.sqlite")
    body = kernel.propose(
        "inference_rule",
        {
            "api_name": "synth_test_late",
            "kind": "property_fact",
            "description": "test rule",
            "source_type": "Package",
            "confidence": 0.9,
            "when_property": {"api_name": "status", "equals": "lost"},
            "then_fact": {"predicate": "lost", "value": "true"},
        },
        0.4,
    )
    kernel.reject_proposal(body["proposal"]["id"], "human")
    assert recorded
    assert recorded[0]["disagreement"] is True
    assert recorded[0]["source"] == "proposal"
    assert recorded[0]["kind"] == "inference_rule"
    assert recorded[0]["actor"] == "human"


def test_reject_pending_action_records_disagreement(tmp_path, monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(
        "quinovo.kernel.record_user_disagreement",
        lambda **kwargs: recorded.append(kwargs),
    )
    dest = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, dest)
    kernel = open_kernel(dest, tmp_path / "pending.sqlite")
    kernel.apply_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        "mcp-agent",
        channel="mcp",
    )
    pending = kernel.list_pending_actions()["actions"]
    assert pending
    kernel.reject_pending_action(pending[0]["id"], "human")
    assert recorded
    assert recorded[0]["disagreement"] is True
    assert recorded[0]["source"] == "pending_action"
    assert recorded[0]["kind"] == "mark_delivered"
