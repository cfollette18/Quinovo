"""When AI may write the world without a human, and when MCP may act."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from quinovo.engine.store import InferredFact, ObjectStore, StoredObject

DEFAULT_AUTO_APPLY_MIN_CONFIDENCE = 0.8

ActionChannel = Literal["human", "mcp"]


class PolicyError(Exception):
    """Action or inference rejected by policy."""


def requires_hitl(confidence: float, threshold: float = DEFAULT_AUTO_APPLY_MIN_CONFIDENCE) -> bool:
    """True when a human must approve. Default: below 80%."""
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1 (0.8 = 80%)")
    return confidence < threshold


def asserted_recommendation(
    store: ObjectStore,
    action_type: str,
    target: StoredObject,
    fact_id: int | None,
) -> InferredFact:
    """MCP may apply a recommended verb only when the fact is asserted."""
    prefix = f"{action_type}:"
    matches = [
        fact
        for fact in store.list_inferred_facts(
            target.object_type, target.id, status="asserted"
        )
        if fact.predicate == "recommended_action" and fact.value.startswith(prefix)
    ]
    if fact_id is not None:
        matches = [fact for fact in matches if fact.id == fact_id]
        if not matches:
            raise PolicyError(
                f"fact {fact_id} is not an asserted {prefix} recommendation on "
                f"{target.object_type}:{target.id}"
            )
    if not matches:
        raise PolicyError(
            f"mcp apply_action {action_type!r} needs an asserted recommended_action "
            f"on {target.object_type}:{target.id}"
        )
    return matches[-1]
