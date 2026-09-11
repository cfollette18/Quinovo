from __future__ import annotations

import shutil
import time
from pathlib import Path

from quinovo.ai.synthesize import (
    STRONG_SYNTH_CONFIDENCE,
    candidate_rules,
    informative,
    namespace_prefix,
    synthesize_and_propose,
)
from quinovo.kernel import open_kernel
from quinovo.llm.author import AUTHORING_MIN_INTERVAL, author_from_index
from quinovo.workspace import WORLD_PACK

EXAMPLE_PACK = Path(__file__).parent / "fixtures" / "example"


def test_namespace_prefix_ignores_hashes():
    assert namespace_prefix("principle:P1") == "principle:"
    assert namespace_prefix("cretex-ticket-routing") == "cretex-"
    assert namespace_prefix("sem-4375ab12") is None
    assert namespace_prefix("fact-3a9c1e2b4d5f") is None
    assert namespace_prefix("fact_s:1_1") is None
    assert namespace_prefix("todo_late", frozenset({"todo"})) is None
    assert namespace_prefix("1Z999") is None


def test_restating_a_property_is_not_informative():
    assert not informative(
        {
            "kind": "property_fact",
            "when_property": {"api_name": "status", "equals": "open"},
            "then_fact": {"predicate": "status", "value": "open"},
        }
    )
    assert informative(
        {
            "kind": "property_fact",
            "when_property": {"api_name": "status", "equals": "open"},
            "then_fact": {"predicate": "needs_owner", "value": "true"},
        }
    )
    assert informative({"kind": "age_fact"})


def test_heuristics_park_for_hitl_and_skip_hash_prefixes(tmp_path):
    kernel = open_kernel(WORLD_PACK, tmp_path / "synth.sqlite")
    for i in range(4):
        kernel.save_turn(
            "s",
            i,
            "quinovo",
            f"Turn {i} about Langfuse.",
            facts=[{"subject": "Langfuse", "predicate": "seen_in", "value": f"turn {i}"}],
            todos=[{"text": f"Chore {i}."}],
            actor="test",
        )
    kinds = {payload["kind"] for _conf, payload in candidate_rules(kernel)}
    assert "property_fact" not in kinds
    assert "prefix_link" not in kinds
    submitted = synthesize_and_propose(kernel)
    assert all(p.confidence <= STRONG_SYNTH_CONFIDENCE for p in submitted)
    assert all(p.status == "pending" for p in submitted)
    assert STRONG_SYNTH_CONFIDENCE < kernel.ontology.ontology.auto_apply_min_confidence


def test_recommend_rules_need_at_risk_evidence(tmp_path):
    dest = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, dest)
    (dest / "inference.yaml").unlink()
    kernel = open_kernel(dest, tmp_path / "db.sqlite")
    kinds = [payload["kind"] for _conf, payload in candidate_rules(kernel)]
    assert "fact_link_fact" not in kinds
    assert "join_links" in kinds


def test_llm_authoring_waits_between_passes(tmp_path, monkeypatch):
    kernel = open_kernel(WORLD_PACK, tmp_path / "interval.sqlite")
    calls: list[str] = []

    class Ready:
        def ready(self) -> bool:
            return True

    monkeypatch.setattr("quinovo.llm.author.load_settings", lambda: Ready())
    monkeypatch.setattr(
        "quinovo.llm.author.llm_propose", lambda k, actor: calls.append(actor) or []
    )
    assert author_from_index(kernel, "t")[1] == "llm"
    kernel.save_turn("s", 1, "quinovo", "A change.", actor="test")
    assert author_from_index(kernel, "t")[1] == "skipped"
    kernel._authoring.last_llm_at = time.monotonic() - AUTHORING_MIN_INTERVAL - 1
    assert author_from_index(kernel, "t")[1] == "llm"
    assert calls == ["t", "t"]
