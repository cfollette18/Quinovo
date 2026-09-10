"""Langfuse tracing for Quinovo LLM calls.

Import Langfuse only after env is loaded. Missing keys disable tracing so
tests and unconfigured machines stay unchanged.
"""

from __future__ import annotations

import atexit
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from quinovo.workspace import ROOT

CompletionRun = Callable[[], tuple[str, dict[str, int], dict[str, Any]]]

_LOADED = False
_ATEXIT = False
_LAST_TRACE_ID: str | None = None
_LAST_OBSERVATION_ID: str | None = None
_SOURCE_TRACES: dict[str, str] = {}


def _parse_env_file(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        value = value.strip().strip("'").strip('"')
        if name:
            found[name] = value
    return found


def load_langfuse_env() -> None:
    """Load ROOT/.env into os.environ without overriding real env vars."""
    global _LOADED
    if _LOADED:
        return
    for key, value in _parse_env_file(ROOT / ".env").items():
        os.environ.setdefault(key, value)
    base = os.environ.get("LANGFUSE_BASE_URL", "").strip()
    if base and not os.environ.get("LANGFUSE_HOST"):
        os.environ["LANGFUSE_HOST"] = base
    os.environ.setdefault("OTEL_SERVICE_NAME", "quinovo")
    _LOADED = True


def tracing_enabled() -> bool:
    load_langfuse_env()
    flag = os.environ.get("LANGFUSE_TRACING_ENABLED", "true").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    )


def tracing_environment() -> str:
    load_langfuse_env()
    return (
        os.environ.get("LANGFUSE_TRACING_ENVIRONMENT")
        or os.environ.get("LANGFUSE_ENVIRONMENT")
        or "development"
    ).strip() or "development"


def _register_flush() -> None:
    global _ATEXIT
    if _ATEXIT:
        return
    atexit.register(flush_langfuse)
    _ATEXIT = True


def flush_langfuse() -> None:
    try:
        if not tracing_enabled():
            return
        client = _client()
        if client is not None:
            client.flush()
    except RuntimeError:
        return


def _client() -> Any:
    """Langfuse client. Imported after env load (SDK reads credentials at import)."""
    load_langfuse_env()
    if not tracing_enabled():
        return None
    from langfuse import get_client

    _register_flush()
    return get_client()


def langfuse_client() -> Any:
    return _client()


def last_trace_id() -> str | None:
    return _LAST_TRACE_ID


def last_observation_id() -> str | None:
    return _LAST_OBSERVATION_ID


def remember_source_trace(source: str, source_id: int, trace_id: str | None) -> None:
    if trace_id:
        _SOURCE_TRACES[f"{source}:{source_id}"] = trace_id


def lookup_source_trace(source: str, source_id: int) -> str | None:
    return _SOURCE_TRACES.get(f"{source}:{source_id}")


def _capture_current_ids(client: Any) -> None:
    global _LAST_TRACE_ID, _LAST_OBSERVATION_ID
    getter = getattr(client, "get_current_trace_id", None)
    if callable(getter):
        _LAST_TRACE_ID = getter()
    obs = getattr(client, "get_current_observation_id", None)
    if callable(obs):
        _LAST_OBSERVATION_ID = obs()


def usage_from_provider(protocol: str, payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {}
    details: dict[str, int] = {}
    if protocol == "anthropic":
        mapping = (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"))
    else:
        mapping = (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"))
    for src, dest in mapping:
        value = usage.get(src)
        if isinstance(value, int):
            details[dest] = value
    return details


@contextmanager
def trace_operation(
    name: str,
    *,
    trace_input: Any = None,
    tags: list[str] | None = None,
) -> Iterator[Any]:
    """Parent span for a Quinovo feature. No-op when Langfuse is not configured."""
    if not tracing_enabled():
        yield None
        return
    from langfuse import propagate_attributes

    client = _client()
    if client is None:
        yield None
        return
    label_tags = ["quinovo", *(tags or []), name]
    with client.start_as_current_observation(
        as_type="span",
        name=name,
        input=trace_input,
    ) as span, propagate_attributes(
        tags=label_tags,
        environment=tracing_environment(),
        metadata={"feature": name},
        trace_name=name,
    ):
        _capture_current_ids(client)
        yield span


def observe_generation(
    *,
    name: str,
    model: str,
    protocol: str,
    provider: str,
    prompt: str,
    run: CompletionRun,
) -> str:
    """Run an LLM call as a Langfuse generation, or untraced if disabled."""
    if not tracing_enabled():
        text, _usage, _raw = run()
        return text
    from langfuse import propagate_attributes

    client = _client()
    if client is None:
        text, _usage, _raw = run()
        return text
    messages = [{"role": "user", "content": prompt}]
    with client.start_as_current_observation(
        as_type="generation",
        name=name,
        model=model,
        input=messages,
        metadata={"protocol": protocol, "provider": provider, "feature": name},
    ) as generation, propagate_attributes(
        tags=["quinovo", name],
        environment=tracing_environment(),
        metadata={"feature": name, "protocol": protocol, "provider": provider},
        trace_name=name,
    ):
        _capture_current_ids(client)
        try:
            text, usage, _raw = run()
        except Exception as exc:
            generation.update(level="ERROR", status_message=str(exc)[:400])
            client.flush()
            raise
        update: dict[str, Any] = {"output": text}
        if usage:
            update["usage_details"] = usage
        generation.update(**update)
        client.flush()
        return text
