from __future__ import annotations

from typing import Any, Literal

from quinovo.engine.store import Forecast, ObjectStore, Proposal, StoredObject
from quinovo.language.models import ObjectTypeDef
from quinovo.policy import requires_hitl

ProposalKind = Literal["type_definition", "classification"]


class ProposalError(Exception):
    """AI proposal rejected or not found."""


def submit_proposal(
    store: ObjectStore,
    kind: ProposalKind,
    payload: dict[str, Any],
    confidence: float,
    actor: str = "quinovo-ai",
) -> tuple[Proposal, list[StoredObject]]:
    """
    New types and classifications: auto-apply at >= threshold (default 80%),
    otherwise park for HITL.
    """
    threshold = store.ontology.ontology.auto_apply_min_confidence
    try:
        hitl = requires_hitl(confidence, threshold)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc

    if kind not in ("type_definition", "classification"):
        raise ProposalError(f"unknown proposal kind {kind!r}")

    if hitl:
        proposal = store.insert_proposal(kind, payload, confidence, actor, "pending")
        store.append_audit(
            "ai_propose",
            actor,
            {"kind": kind, "confidence": confidence, "proposal_id": proposal.id},
            "pending_hitl",
        )
        return proposal, []

    edited = _execute(store, kind, payload)
    proposal = store.insert_proposal(kind, payload, confidence, actor, "auto_applied")
    store.append_audit(
        "ai_propose",
        actor,
        {"kind": kind, "confidence": confidence, "proposal_id": proposal.id},
        "auto_applied",
    )
    return proposal, edited


def approve_proposal(
    store: ObjectStore,
    proposal_id: int,
    actor: str,
) -> tuple[Proposal, list[StoredObject]]:
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalError(f"missing proposal {proposal_id}")
    if proposal.status != "pending":
        raise ProposalError(f"proposal {proposal_id} is {proposal.status}, not pending")
    kind: ProposalKind
    if proposal.kind == "type_definition":
        kind = "type_definition"
    elif proposal.kind == "classification":
        kind = "classification"
    else:
        raise ProposalError(f"unknown proposal kind {proposal.kind!r}")
    edited = _execute(store, kind, proposal.payload)
    updated = store.set_proposal_status(proposal_id, "approved", actor)
    store.append_audit(
        "approve_proposal",
        actor,
        {"proposal_id": proposal_id},
        "applied",
    )
    return updated, edited


def reject_proposal(store: ObjectStore, proposal_id: int, actor: str) -> Proposal:
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalError(f"missing proposal {proposal_id}")
    if proposal.status != "pending":
        raise ProposalError(f"proposal {proposal_id} is {proposal.status}, not pending")
    updated = store.set_proposal_status(proposal_id, "rejected", actor)
    store.append_audit(
        "reject_proposal",
        actor,
        {"proposal_id": proposal_id},
        "rejected",
    )
    return updated


def write_forecast(
    store: ObjectStore,
    object_type: str,
    pk: str,
    metric: str,
    horizon_hours: float,
    point: float,
    model: str,
    confidence: float,
    q10: float | None = None,
    q90: float | None = None,
) -> Forecast:
    """A forecast is a measure on the object, with lineage."""
    try:
        requires_hitl(confidence, store.ontology.ontology.auto_apply_min_confidence)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    try:
        forecast = store.put_forecast(
            object_type,
            pk,
            metric,
            horizon_hours,
            point,
            model,
            confidence,
            q10=q10,
            q90=q90,
        )
    except KeyError as exc:
        raise ProposalError(str(exc)) from exc
    store.append_audit(
        "write_forecast",
        "quinovo-ai",
        {"forecast_id": forecast.id, "metric": metric, "confidence": confidence},
        "applied",
    )
    return forecast


def forecast_actionable(store: ObjectStore, forecast: Forecast) -> bool:
    """Agents may auto-act on a forecast only when it clears the same 80% bar."""
    return not requires_hitl(
        forecast.confidence,
        store.ontology.ontology.auto_apply_min_confidence,
    )


def _execute(
    store: ObjectStore,
    kind: ProposalKind,
    payload: dict[str, Any],
) -> list[StoredObject]:
    if kind == "type_definition":
        try:
            type_def = ObjectTypeDef.model_validate(payload)
        except Exception as exc:
            raise ProposalError(str(exc)) from exc
        store.register_object_type(type_def)
        return []
    object_type = payload.get("object_type")
    properties = payload.get("properties")
    if not isinstance(object_type, str) or not isinstance(properties, dict):
        raise ProposalError("classification payload needs object_type and properties")
    try:
        return [store.upsert_object(object_type, properties)]
    except (KeyError, ValueError) as exc:
        raise ProposalError(str(exc)) from exc
