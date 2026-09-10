from __future__ import annotations

from contextlib import contextmanager

from quinovo.llm.engine import LLMEngine, status_payload
from quinovo.llm.settings import LLMSettings
from quinovo.llm.tracing import observe_generation, usage_from_provider


def test_usage_from_anthropic_and_openai():
    assert usage_from_provider(
        "anthropic",
        {"usage": {"input_tokens": 11, "output_tokens": 3}},
    ) == {"input_tokens": 11, "output_tokens": 3}
    assert usage_from_provider(
        "openai",
        {"usage": {"prompt_tokens": 8, "completion_tokens": 2}},
    ) == {"input_tokens": 8, "output_tokens": 2}
    assert usage_from_provider("anthropic", {}) == {}


def test_observe_generation_records_model_tokens_and_output(monkeypatch):
    recorded: dict = {}

    class FakeGeneration:
        def update(self, **kwargs):
            recorded["update"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeClient:
        def start_as_current_observation(self, **kwargs):
            recorded["start"] = kwargs
            return FakeGeneration()

        def flush(self):
            recorded["flushed"] = True

    @contextmanager
    def fake_propagate(**kwargs):
        recorded["attrs"] = kwargs
        yield

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    monkeypatch.setattr("quinovo.llm.tracing._client", lambda: FakeClient())
    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate, raising=False)

    def run():
        return "ok", {"input_tokens": 4, "output_tokens": 1}, {}

    text = observe_generation(
        name="test-connection",
        model="MiniMax-M3",
        protocol="anthropic",
        provider="minimax",
        prompt="Reply with the single word ok.",
        run=run,
    )
    assert text == "ok"
    assert recorded["start"]["as_type"] == "generation"
    assert recorded["start"]["name"] == "test-connection"
    assert recorded["start"]["model"] == "MiniMax-M3"
    assert recorded["start"]["input"] == [
        {"role": "user", "content": "Reply with the single word ok."}
    ]
    assert recorded["update"]["output"] == "ok"
    assert recorded["update"]["usage_details"] == {
        "input_tokens": 4,
        "output_tokens": 1,
    }
    assert "quinovo" in recorded["attrs"]["tags"]
    assert recorded["flushed"] is True


def test_engine_complete_sends_usage_when_traced(monkeypatch):
    recorded: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 5, "output_tokens": 1},
            }

    class FakeGeneration:
        def update(self, **kwargs):
            recorded["update"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeClient:
        def start_as_current_observation(self, **kwargs):
            recorded["start"] = kwargs
            return FakeGeneration()

        def flush(self):
            recorded["flushed"] = True

    @contextmanager
    def fake_propagate(**kwargs):
        yield

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", lambda *a, **k: FakeResponse())
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setattr("quinovo.llm.tracing.tracing_enabled", lambda: True)
    monkeypatch.setattr("quinovo.llm.tracing._client", lambda: FakeClient())
    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate, raising=False)

    engine = LLMEngine(
        LLMSettings(
            provider="minimax",
            model="MiniMax-M3",
            base_url="https://api.minimax.io/anthropic",
            api_key="k",
            protocol="anthropic",
        )
    )
    assert engine.complete("hi", feature="test-connection") == "ok"
    assert recorded["start"]["name"] == "test-connection"
    assert recorded["update"]["usage_details"]["input_tokens"] == 5
    assert "k" not in str(recorded["start"]["input"])
    assert recorded["flushed"] is True


def test_status_payload_includes_tracing_without_keys():
    payload = status_payload(LLMSettings(api_key=""))
    assert "enabled" in payload["tracing"]
    assert "environment" in payload["tracing"]
    assert payload["tracing"]["disagreement_dataset"]
    assert "LANGFUSE" not in str(payload)
    assert "sk-lf-" not in str(payload)
    assert "pk-lf-" not in str(payload)
