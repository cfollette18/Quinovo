"""LLM reasons over the ontology and proposes applying an action. HITL below 0.8."""

from __future__ import annotations

import shutil

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel


@pytest.fixture
def kernel(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "act.sqlite")


def test_propose_action_below_threshold_is_hitl(kernel):
    body = kernel.propose_action(
        "mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, 0.4, actor="quinovo-ai", reason="late"
    )
    assert body["hitl"] is True
    assert body["proposal"]["status"] == "pending"
    assert body["proposal"]["kind"] == "action_application"
    # Nothing applied yet.
    obj = kernel.get_object("Package", "1Z999")
    assert obj["properties"]["status"] != "delivered"


def test_approve_action_proposal_applies_it(kernel):
    body = kernel.propose_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, 0.4)
    proposal_id = body["proposal"]["id"]
    approved = kernel.approve_proposal(proposal_id, "human")
    assert approved["proposal"]["status"] == "approved"
    obj = kernel.get_object("Package", "1Z999")
    assert obj["properties"]["status"] == "delivered"


def test_propose_action_above_threshold_parks_plain_action(kernel):
    # mark_delivered is a plain action (not unattended, not mcp_requires_recommendation).
    # Even at high confidence the action policy is sovereign: it parks for a human.
    body = kernel.propose_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, 0.9)
    assert body["hitl"] is True
    assert body["proposal"]["status"] == "pending"
    obj = kernel.get_object("Package", "1Z999")
    assert obj["properties"]["status"] != "delivered"


def test_propose_action_auto_applies_unattended_with_recommendation(kernel):
    # notify_buyer is unattended + mcp_requires_recommendation. With an asserted
    # recommendation fact, a high-confidence proposal auto-applies.
    kernel.write_forecast("Package", "1Z999", "late_risk", 24, 0.4, "timesfm-2.5", 0.88)
    kernel.run_inference()
    body = kernel.propose_action(
        "notify_buyer", {"package": {"type": "Package", "id": "1Z999"}}, 0.9, actor="quinovo-ai", reason="late"
    )
    assert body["hitl"] is False
    assert body["proposal"]["status"] == "auto_applied"
    obj = kernel.get_object("Package", "1Z999")
    assert obj["properties"]["buyer_notified"] == "true"


def test_propose_action_bad_payload_raises(kernel):
    with pytest.raises(Exception):
        kernel.propose_action("", {"package": {"type": "Package", "id": "1Z999"}}, 0.9)


def test_reject_action_proposal_does_not_apply(kernel):
    body = kernel.propose_action("mark_delivered", {"package": {"type": "Package", "id": "1Z999"}}, 0.4)
    kernel.reject_proposal(body["proposal"]["id"], "human")
    obj = kernel.get_object("Package", "1Z999")
    assert obj["properties"]["status"] != "delivered"


def test_tick_returns_source_and_logic_surfaces(kernel):
    result = kernel.tick()
    assert "sources_pulled" in result
    assert "logic_ran" in result
