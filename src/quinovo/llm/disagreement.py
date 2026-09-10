"""Langfuse dataset of human disagreements — training signal for the agent.

When a human turns down a proposal or pending action, disagreement is true
and the case is saved to the Langfuse dataset `training/user-disagreement`.
"""

from __future__ import annotations

import os
from typing import Any

from quinovo.llm import tracing as lf
from quinovo.train.filters import _scrub

DEFAULT_DISAGREEMENT_DATASET = "training/user-disagreement"
SCORE_NAME = "user-disagreement"


def disagreement_dataset_name() -> str:
    return (
        os.environ.get("LANGFUSE_DISAGREEMENT_DATASET", DEFAULT_DISAGREEMENT_DATASET).strip()
        or DEFAULT_DISAGREEMENT_DATASET
    )


DISAGREEMENT_DATASET = DEFAULT_DISAGREEMENT_DATASET

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "enum": ["proposal", "pending_action"]},
        "kind": {"type": "string"},
        "title": {"type": "string"},
        "why": {"type": "string"},
        "what": {"type": "string"},
        "confidence": {"type": "number"},
        "payload": {"type": "object"},
    },
    "required": ["source", "kind"],
}
EXPECTED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "disagreement": {"type": "boolean"},
        "decision": {"type": "string", "enum": ["reject"]},
        "should_propose": {"type": "boolean"},
    },
    "required": ["disagreement", "decision", "should_propose"],
}

_DATASET_READY = False


def _item_id(source: str, source_id: int) -> str:
    return f"quinovo-{source}-{source_id}"


def ensure_disagreement_dataset(client: Any | None = None) -> bool:
    """Create the Langfuse training dataset if it is missing. Never raises."""
    global _DATASET_READY
    if _DATASET_READY:
        return True
    if not lf.tracing_enabled():
        return False
    item = client if client is not None else lf.langfuse_client()
    if item is None:
        return False
    name = disagreement_dataset_name()
    try:
        try:
            item.get_dataset(name, fetch_items_page_size=1)
        except Exception:
            item.create_dataset(
                name=name,
                description=(
                    "Human disagreements with Quinovo proposals. "
                    "Each item is a case a person turned down — training data "
                    "so the agent learns not to propose the same thing again."
                ),
                metadata={
                    "author": "quinovo",
                    "type": "training",
                    "signal": SCORE_NAME,
                },
                input_schema=INPUT_SCHEMA,
                expected_output_schema=EXPECTED_OUTPUT_SCHEMA,
            )
        _DATASET_READY = True
        return True
    except Exception:
        return False


def record_user_disagreement(
    *,
    disagreement: bool,
    source: str,
    source_id: int,
    actor: str,
    kind: str,
    title: str = "",
    why: str = "",
    what: str = "",
    confidence: float | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """If disagreement is true, score the trace and save a Langfuse training item.

    Failures never block the human reject path.
    """
    if not disagreement:
        return
    if not lf.tracing_enabled():
        return
    client = lf.langfuse_client()
    if client is None:
        return
    try:
        _save_disagreement(
            client,
            source=source,
            source_id=source_id,
            actor=actor,
            kind=kind,
            title=title,
            why=why,
            what=what,
            confidence=confidence,
            payload=payload or {},
        )
    except Exception:
        return


def _save_disagreement(
    client: Any,
    *,
    source: str,
    source_id: int,
    actor: str,
    kind: str,
    title: str,
    why: str,
    what: str,
    confidence: float | None,
    payload: dict[str, Any],
) -> None:
    ensure_disagreement_dataset(client)
    item_input: dict[str, Any] = {
        "source": source,
        "kind": kind,
        "title": title,
        "why": why,
        "what": what,
        "payload": _scrub(payload) if isinstance(payload, dict) else {},
    }
    if confidence is not None:
        item_input["confidence"] = confidence
    expected = {
        "disagreement": True,
        "decision": "reject",
        "should_propose": False,
    }
    origin_trace = lf.lookup_source_trace(source, source_id)
    comment = f"{actor} turned down this {source.replace('_', ' ')}."
    span_trace: str | None = None
    span_observation: str | None = None
    with lf.trace_operation(
        "user-disagreement",
        trace_input=item_input,
        tags=["user-disagreement", "training"],
    ) as span:
        if span is not None:
            updater = getattr(span, "update", None)
            if callable(updater):
                updater(output=expected)
            getter = getattr(client, "get_current_trace_id", None)
            if callable(getter):
                span_trace = getter()
            obs = getattr(client, "get_current_observation_id", None)
            if callable(obs):
                span_observation = obs()
        _score_trace(
            client,
            trace_id=origin_trace or span_trace,
            observation_id=span_observation if not origin_trace else None,
            comment=comment,
            metadata={"source": source, "source_id": source_id, "actor": actor},
        )
        if origin_trace and span_trace and origin_trace != span_trace:
            _score_trace(
                client,
                trace_id=span_trace,
                observation_id=span_observation,
                comment=comment,
                metadata={"source": source, "source_id": source_id, "actor": actor},
            )
        client.create_dataset_item(
            dataset_name=disagreement_dataset_name(),
            id=_item_id(source, source_id),
            input=item_input,
            expected_output=expected,
            metadata={
                "source": source,
                "source_id": source_id,
                "actor": actor,
                "disagreement": True,
                "environment": lf.tracing_environment(),
            },
            source_trace_id=origin_trace or span_trace,
            source_observation_id=span_observation if not origin_trace else None,
        )
    lf.flush_langfuse()


def _score_trace(
    client: Any,
    *,
    trace_id: str | None,
    observation_id: str | None,
    comment: str,
    metadata: dict[str, Any],
) -> None:
    if not trace_id:
        return
    kwargs: dict[str, Any] = {
        "name": SCORE_NAME,
        "value": 1,
        "data_type": "BOOLEAN",
        "comment": comment,
        "trace_id": trace_id,
        "metadata": metadata,
        "environment": lf.tracing_environment(),
    }
    if observation_id:
        kwargs["observation_id"] = observation_id
    client.create_score(**kwargs)
