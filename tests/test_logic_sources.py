"""External logic sources: logic can live anywhere and feed the ontology."""

from __future__ import annotations

import shutil

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel
from quinovo.logic.base import LogicResult


@pytest.fixture
def kernel(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "logic.sqlite")


def test_register_and_run_callable_logic(kernel):
    def source(store, record):
        store.upsert_inferred_fact(
            "Package", "1Z999", "custom_risk", "true", 0.9, record.name, "logic:test", "asserted",
        )
        return LogicResult(facts=[{"predicate": "custom_risk", "value": "true"}], detail="ok")

    kernel.register_logic_callable("risk-model", source, description="a custom model")
    listed = kernel.list_logic_sources()["logic_sources"]
    assert len(listed) == 1
    result = kernel.run_logic_source("risk-model")
    assert result["facts"]
    fact = kernel.get_object("Package", "1Z999")["facts"]
    predicates = {f["predicate"] for f in fact}
    assert "custom_risk" in predicates


def test_run_unknown_logic_source(kernel):
    with pytest.raises(KeyError):
        kernel.run_logic_source("nope")


def test_register_logic_unknown_kind(kernel):
    with pytest.raises(ValueError):
        kernel.register_logic_source("bad", "ftp", {})


def test_run_all_logic_only_runs_auto(kernel):
    kernel.register_logic_callable("manual", lambda store, rec: LogicResult(detail="m"))
    kernel.register_logic_callable(
        "auto",
        lambda store, rec: LogicResult(facts=[{"predicate": "x", "value": "1"}], detail="a"),
        auto=True,
    )
    result = kernel.run_all_logic()
    names = [item["source"] for item in result["ran"]]
    assert "auto" in names
    assert "manual" not in names


def test_delete_logic_source(kernel):
    kernel.register_logic_callable("temp", lambda store, rec: LogicResult(detail=""))
    kernel.delete_logic_source("temp")
    assert kernel.list_logic_sources()["logic_sources"] == []


def test_http_logic_source_ingests_facts(kernel, monkeypatch):
    kernel.register_logic_source(
        "remote",
        "http",
        {"url": "https://example.invalid/logic", "object_type": "Package", "rule": "remote_rule"},
    )

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "facts": [
                    {
                        "object_type": "Package",
                        "id": "1Z999",
                        "predicate": "remote_risk",
                        "value": "true",
                        "confidence": 0.91,
                    }
                ],
                "forecasts": [],
            }

    def fake_post(url, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("quinovo.logic.http_source.httpx.post", fake_post)
    result = kernel.run_logic_source("remote")
    assert result["facts"]
    fact = next(
        f for f in kernel.store.list_inferred_facts("Package", "1Z999") if f.predicate == "remote_risk"
    )
    assert fact.rule == "remote_rule"
    assert fact.status == "asserted"
