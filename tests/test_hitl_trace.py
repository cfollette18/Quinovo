from __future__ import annotations

import shutil
from contextlib import contextmanager

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel


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

    def start_as_current_observation(self, **kwargs):
        self.recorded["spans"].append(kwargs)
        span = FakeSpan()
        self.recorded["span_objs"].append(span)
        return span

    def get_current_trace_id(self):
        return "trace-pending-hitl"

    def get_current_observation_id(self):
        return "obs-pending-hitl"

    def flush(self):
        self.recorded["flushed"] = True


@pytest.fixture
def kernel(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "act.sqlite")


@pytest.fixture
def langfuse(monkeypatch):
    recorded: dict = {"spans": [], "span_objs": [], "flushed": False, "attrs": []}
    client = FakeClient(recorded)

    @contextmanager
    def fake_propagate(**kwargs):
        recorded["attrs"].append(kwargs)
        yield

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    monkeypatch.setattr("quinovo.llm.tracing._client", lambda: client)
    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate, raising=False)
    return recorded


def test_low_confidence_proposal_emits_pending_hitl_span(kernel, langfuse):
    body = kernel.propose_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        0.4,
        actor="quinovo-ai",
        reason="late",
    )
    assert body["hitl"] is True
    assert langfuse["spans"]
    start = langfuse["spans"][0]
    assert start["name"] == "pending_hitl"
    assert start["input"]["kind"] == "action_application"
    assert start["input"]["confidence"] == 0.4
    assert "mark_delivered" in str(start["input"]["title"])
    assert langfuse["span_objs"][0].updates[0]["output"]["hitl"] is True
    tags = langfuse["attrs"][0]["tags"]
    assert "quinovo" in tags
    assert "hitl" in tags
    assert "inference" in tags
    assert langfuse["flushed"] is True


def test_auto_applied_proposal_does_not_emit_pending_hitl(kernel, langfuse):
    kernel.write_forecast("Package", "1Z999", "late_risk", 24, 0.4, "timesfm-2.5", 0.88)
    kernel.run_inference()
    langfuse["spans"].clear()
    langfuse["span_objs"].clear()
    langfuse["attrs"].clear()
    body = kernel.propose_action(
        "notify_buyer",
        {"package": {"type": "Package", "id": "1Z999"}},
        0.9,
        actor="quinovo-ai",
        reason="late",
    )
    assert body["hitl"] is False
    assert langfuse["spans"] == []


def test_low_confidence_inferred_fact_emits_pending_hitl_span(kernel, langfuse):
    kernel.write_forecast("Package", "1Z999", "late_risk", 24, 0.5, "timesfm-2.5", 0.4)
    facts = kernel.run_inference()["facts"]
    pending = [item for item in facts if item["status"] == "pending"]
    assert pending
    names = [span["name"] for span in langfuse["spans"]]
    assert "pending_hitl" in names
    hitl_span = next(span for span in langfuse["spans"] if span["name"] == "pending_hitl")
    assert hitl_span["input"]["source"] == "inferred_fact"
    assert hitl_span["input"]["kind"] == "inferred_fact"
