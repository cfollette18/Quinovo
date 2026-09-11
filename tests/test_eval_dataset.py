from __future__ import annotations

from quinovo.llm import eval_dataset as eval_mod
from quinovo.llm.eval_dataset import (
    DEFAULT_EVAL_DATASET,
    collect_eval_failures,
    ensure_eval_dataset,
    experiment_rule_body,
    fail_values,
    item_id_for,
    load_template,
    observation_item_input,
    passing_output,
    score_failed,
)


def setup_function() -> None:
    eval_mod._DATASET_READY = False


def test_template_covers_every_agent_run_judge():
    template = load_template()
    triggers = {item["template"]: item for item in template["triggers"]}
    assert template["name"] == DEFAULT_EVAL_DATASET
    assert set(triggers) == {
        "save_turn_called",
        "structured_capture",
        "mcp_bypass",
        "propose_not_author",
        "hitl_respected",
        "named_action",
        "twin_first",
    }
    assert fail_values(triggers["save_turn_called"]) == ["false"]
    assert fail_values(triggers["mcp_bypass"]) == ["true"]
    assert fail_values(triggers["structured_capture"]) == ["partial", "skipped"]
    assert score_failed(triggers["save_turn_called"], False)
    assert not score_failed(triggers["save_turn_called"], True)
    assert score_failed(triggers["mcp_bypass"], True)
    assert score_failed(triggers["structured_capture"], "partial")
    assert not score_failed(triggers["structured_capture"], "complete")
    expected = passing_output(template)
    assert expected["save_turn_called"] is True
    assert expected["mcp_bypass"] is False
    assert expected["structured_capture"] == "complete"


def test_experiment_rule_filters_to_the_dataset():
    body = experiment_rule_body("ds-1", ["eval-a", "eval-b"], name="quinovo/eval-failures")
    assert body["enabled"] is True
    assert body["sampling"] == 1
    columns = {item["column"]: item for item in body["filter"]}
    assert columns["isExperimentItemRootSpan"]["value"] is True
    assert columns["datasetId"]["value"] == ["ds-1"]
    assert [item["evaluatorId"] for item in body["evaluatorAssignments"]] == [
        "eval-a",
        "eval-b",
    ]


def test_observation_maps_to_judge_variables():
    payload = observation_item_input(
        {
            "input": "Save this turn.",
            "output": "Done.",
            "metadata": {"tool_calls": [{"name": "save_turn"}]},
        }
    )
    assert payload["user_input"] == "Save this turn."
    assert payload["output"] == "Done."
    assert payload["tool_calls"] == [{"name": "save_turn"}]
    assert item_id_for("obs-1", "trace-1") == "quinovo-eval-obs-1"


def test_ensure_creates_dataset_once(monkeypatch):
    recorded: dict = {"datasets": [], "dataset_exists": False}

    class FakeClient:
        def get_dataset(self, name: str, fetch_items_page_size: int = 50):
            if recorded["dataset_exists"]:
                return {"name": name, "id": "ds-1"}
            raise LookupError("missing dataset")

        def create_dataset(self, **kwargs):
            recorded["datasets"].append(kwargs)
            recorded["dataset_exists"] = True
            return {"name": kwargs.get("name"), "id": "ds-1"}

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    assert ensure_eval_dataset(FakeClient()) is True
    assert ensure_eval_dataset(FakeClient()) is True
    assert len(recorded["datasets"]) == 1
    created = recorded["datasets"][0]
    assert created["name"] == DEFAULT_EVAL_DATASET
    assert "user_input" in created["input_schema"]["properties"]
    assert "save_turn_called" in created["expected_output_schema"]["properties"]


def test_collect_upserts_failing_runs(monkeypatch):
    posted: list[dict] = []
    pages = {
        "/api/public/v3/scores": [
            {
                "name": "save_turn_called",
                "value": False,
                "environment": "development",
                "subject": {
                    "kind": "observation",
                    "id": "obs-9",
                    "traceId": "trace-9",
                },
            }
        ],
        "/api/public/v2/observations": [
            {
                "id": "obs-9",
                "traceId": "trace-9",
                "isRootObservation": True,
                "environment": "development",
                "input": "Capture this.",
                "output": "I forgot save_turn.",
                "metadata": {"tool_calls": []},
            }
        ],
    }

    def fake_request(**kwargs):
        url = str(kwargs.get("url") or "")
        method = kwargs.get("method")
        if method == "GET" and "/api/public/v3/scores" in url:
            if "name=save_turn_called" in url:
                return 200, {"data": pages["/api/public/v3/scores"], "meta": {}}
            return 200, {"data": [], "meta": {}}
        if method == "GET" and "/api/public/v2/observations" in url:
            return 200, {"data": pages["/api/public/v2/observations"], "meta": {}}
        if method == "POST" and url.endswith("/api/public/dataset-items"):
            posted.append(kwargs["body"])
            return 200, {"id": kwargs["body"]["id"]}
        return 404, {}

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    monkeypatch.setattr(eval_mod, "ensure_eval_dataset", lambda client=None: True)
    monkeypatch.setattr(eval_mod, "request_json", fake_request)
    monkeypatch.setattr("quinovo.llm.tracing.flush_langfuse", lambda: None)

    result = collect_eval_failures(since_hours=1, limit=10)
    assert result["items"] == 1
    assert result["scores"] == 1
    item = posted[0]
    assert item["datasetName"] == DEFAULT_EVAL_DATASET
    assert item["id"] == "quinovo-eval-obs-9"
    assert item["input"]["user_input"] == "Capture this."
    assert item["expectedOutput"]["save_turn_called"] is True
    assert item["metadata"]["failed"] == ["save_turn_called"]
    assert item["sourceTraceId"] == "trace-9"
    assert item["sourceObservationId"] == "obs-9"


def test_collect_skips_when_tracing_off(monkeypatch):
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: False)
    result = collect_eval_failures()
    assert result["items"] == 0
    assert result["scores"] == 0
