from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from quinovo.engine.store import Forecast, ObjectStore, Proposal, StoredObject
from quinovo.language.models import PROPOSAL_KINDS, ProposalKind
from quinovo.llm.tracing import pack_context, trace_pending_hitl
from quinovo.pack.authoring import PackCreateError, apply_kind
from quinovo.policy import ActionChannel, requires_hitl


class ProposalError(Exception):
    """AI proposal rejected or not found."""


class ProposalKernel(Protocol):
    pack_dir: Path
    store: ObjectStore

    def reload(self) -> None: ...

    def apply_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        actor: str = "local",
        *,
        channel: ActionChannel = "human",
        fact_id: int | None = None,
        already_approved: bool = False,
    ) -> dict[str, Any]: ...


def _as_kind(kind: str) -> ProposalKind:
    if kind in PROPOSAL_KINDS:
        return kind  # type: ignore[return-value]
    raise ProposalError(f"unknown proposal kind {kind!r}")


def _trace_parked_proposal(kernel: ProposalKernel, proposal: Proposal) -> None:
    payload = proposal.payload or {}
    trace_pending_hitl(
        source="proposal",
        source_id=proposal.id,
        item={
            "source": "proposal",
            "id": proposal.id,
            "kind": proposal.kind,
            "title": payload.get("api_name") or payload.get("action_type") or proposal.kind,
            "why": payload.get("reason") or "",
            "what": payload.get("description") or "",
            "confidence": proposal.confidence,
            "payload": payload,
            "actor": proposal.actor,
            "pack_context": pack_context(kernel.store),
        },
    )


def _execute(
    kernel: ProposalKernel,
    kind: ProposalKind,
    payload: dict[str, Any],
) -> list[StoredObject]:
    try:
        edited, needs_reload = apply_kind(kernel.pack_dir, kernel.store, kind, payload)
    except (PackCreateError, KeyError, TypeError, ValueError) as exc:
        raise ProposalError(str(exc)) from exc
    if needs_reload:
        kernel.reload()
    return edited


def submit_proposal(
    kernel: ProposalKernel,
    kind: str,
    payload: dict[str, Any],
    confidence: float,
    actor: str = "quinovo-ai",
) -> tuple[Proposal, list[StoredObject]]:
    """Pack and rule changes: auto-apply at >= threshold (default 80%), else park for HITL."""
    resolved = _as_kind(kind)
    if resolved == "action_application":
        return _submit_action_application(kernel, payload, confidence, actor)
    threshold = kernel.store.ontology.ontology.auto_apply_min_confidence
    try:
        hitl = requires_hitl(confidence, threshold)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc

    if hitl:
        proposal = kernel.store.insert_proposal(resolved, payload, confidence, actor, "pending")
        kernel.store.append_audit(
            "ai_propose",
            actor,
            {"kind": resolved, "confidence": confidence, "proposal_id": proposal.id},
            "pending_hitl",
        )
        _trace_parked_proposal(kernel, proposal)
        return proposal, []

    edited = _execute(kernel, resolved, payload)
    proposal = kernel.store.insert_proposal(resolved, payload, confidence, actor, "auto_applied")
    kernel.store.append_audit(
        "ai_propose",
        actor,
        {"kind": resolved, "confidence": confidence, "proposal_id": proposal.id},
        "auto_applied",
    )
    return proposal, edited


def _submit_action_application(
    kernel: ProposalKernel,
    payload: dict[str, Any],
    confidence: float,
    actor: str,
) -> tuple[Proposal, list[StoredObject]]:
    """The LLM reasons over the ontology and proposes applying a named action.

    Below the threshold this parks as a HITL proposal; approving it applies the
    action. At/above the threshold the action is applied immediately through the
    same audited path an agent would use. approval_required actions still park.
    """
    action_type = payload.get("action_type")
    parameters = payload.get("parameters") or {}
    if not isinstance(action_type, str) or not action_type:
        raise ProposalError("action_application payload needs action_type")
    if not isinstance(parameters, dict):
        raise ProposalError("action_application parameters must be a mapping")
    threshold = kernel.store.ontology.ontology.auto_apply_min_confidence
    try:
        hitl = requires_hitl(confidence, threshold)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    if hitl:
        proposal = kernel.store.insert_proposal(
            "action_application", payload, confidence, actor, "pending"
        )
        kernel.store.append_audit(
            "ai_propose",
            actor,
            {"kind": "action_application", "action_type": action_type, "proposal_id": proposal.id},
            "pending_hitl",
        )
        _trace_parked_proposal(kernel, proposal)
        return proposal, []
    # The action's own policy is sovereign: only actions the loop could auto-apply
    # (unattended, or mcp_requires_recommendation) are auto-applied at >=0.8.
    # approval_required and plain actions still park for a human.
    try:
        spec = kernel.store.ontology.action_type(action_type)
    except KeyError as exc:
        raise ProposalError(f"unknown action type {action_type!r}") from exc
    auto_apply = spec.unattended or spec.mcp_requires_recommendation
    if not auto_apply:
        proposal = kernel.store.insert_proposal(
            "action_application", payload, confidence, actor, "pending"
        )
        kernel.store.append_audit(
            "ai_propose",
            actor,
            {"kind": "action_application", "action_type": action_type, "proposal_id": proposal.id},
            "pending_hitl",
        )
        _trace_parked_proposal(kernel, proposal)
        return proposal, []
    try:
        result = kernel.apply_action(action_type, parameters, actor, channel="mcp", already_approved=True)
    except Exception:  # noqa: BLE001 — policy parked it (e.g. missing recommendation)
        proposal = kernel.store.insert_proposal(
            "action_application", payload, confidence, actor, "pending"
        )
        kernel.store.append_audit(
            "ai_propose",
            actor,
            {"kind": "action_application", "action_type": action_type, "proposal_id": proposal.id},
            "pending_hitl",
        )
        _trace_parked_proposal(kernel, proposal)
        return proposal, []
    proposal = kernel.store.insert_proposal(
        "action_application", payload, confidence, actor, "auto_applied"
    )
    kernel.store.append_audit(
        "ai_propose",
        actor,
        {"kind": "action_application", "action_type": action_type, "proposal_id": proposal.id},
        "auto_applied",
    )
    edited = [
        kernel.store.get_object(obj["type"], obj["id"])  # type: ignore[arg-type]
        for obj in result.get("objects", [])
    ]
    edited = [item for item in edited if item is not None]
    return proposal, edited


def approve_proposal(
    kernel: ProposalKernel,
    proposal_id: int,
    actor: str,
) -> tuple[Proposal, list[StoredObject]]:
    proposal = kernel.store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalError(f"missing proposal {proposal_id}")
    if proposal.status != "pending":
        raise ProposalError(f"proposal {proposal_id} is {proposal.status}, not pending")
    if proposal.kind == "action_application":
        payload = proposal.payload
        action_type = payload.get("action_type")
        parameters = payload.get("parameters") or {}
        if not isinstance(action_type, str) or not action_type:
            raise ProposalError("action_application payload needs action_type")
        result = kernel.apply_action(
            action_type, parameters, actor, channel="human", already_approved=True
        )
        updated = kernel.store.set_proposal_status(proposal_id, "approved", actor)
        kernel.store.append_audit(
            "approve_proposal",
            actor,
            {"proposal_id": proposal_id, "action_type": action_type},
            "applied",
        )
        edited = [
            kernel.store.get_object(obj["type"], obj["id"])  # type: ignore[arg-type]
            for obj in result.get("objects", [])
        ]
        edited = [item for item in edited if item is not None]
        return updated, edited
    kind = _as_kind(proposal.kind)
    edited = _execute(kernel, kind, proposal.payload)
    updated = kernel.store.set_proposal_status(proposal_id, "approved", actor)
    kernel.store.append_audit(
        "approve_proposal",
        actor,
        {"proposal_id": proposal_id},
        "applied",
    )
    return updated, edited


def reject_proposal(kernel: ProposalKernel, proposal_id: int, actor: str) -> Proposal:
    proposal = kernel.store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalError(f"missing proposal {proposal_id}")
    if proposal.status != "pending":
        raise ProposalError(f"proposal {proposal_id} is {proposal.status}, not pending")
    updated = kernel.store.set_proposal_status(proposal_id, "rejected", actor)
    kernel.store.append_audit(
        "reject_proposal",
        actor,
        {"proposal_id": proposal_id},
        "rejected",
    )
    return updated


def write_forecast(
    store: ObjectStore,
    object_type: str,
    id: str,
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
            id,
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
