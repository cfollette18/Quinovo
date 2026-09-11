from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from quinovo.actions.dispatch import DispatchError, dispatch
from quinovo.engine.store import AuditRow, ObjectStore, StoredObject
from quinovo.language.models import ActionParameterDef, ObjectRef
from quinovo.llm.tracing import pack_context, trace_pending_hitl
from quinovo.policy import ActionChannel, PolicyError, asserted_recommendation
from quinovo.security import Guard, SecurityError


class ActionError(Exception):
    """Action rejected: unknown type, bad params, missing object, or policy."""


def _trace_parked_action(
    store: ObjectStore,
    pending_id: int,
    action_type: str,
    actor: str,
    parameters: dict[str, Any],
    spec: Any,
) -> None:
    trace_pending_hitl(
        source="pending_action",
        source_id=pending_id,
        item={
            "source": "pending_action",
            "id": pending_id,
            "kind": "pending_action",
            "title": action_type,
            "why": "",
            "what": parameters,
            "confidence": None,
            "payload": {
                "action_type": action_type,
                "parameters": parameters,
                "unattended": spec.unattended,
                "approval_required": spec.approval_required,
            },
            "actor": actor,
            "pack_context": pack_context(store),
        },
    )


def _coerce_scalar(param: ActionParameterDef, raw: Any) -> Any:
    match param.type:
        case "string":
            return str(raw)
        case "integer":
            return int(raw)
        case "number":
            return float(raw)
        case "boolean":
            if isinstance(raw, bool):
                return raw
            return str(raw).lower() in {"true", "1", "yes"}
        case "object":
            raise ActionError(f"parameter {param.api_name} is an object reference")
        case _ as unreachable:
            raise TypeError(f"unhandled param type: {unreachable}")


def apply_action(
    store: ObjectStore,
    action_type: str,
    parameters: dict[str, Any],
    actor: str = "local",
    *,
    channel: ActionChannel = "human",
    fact_id: int | None = None,
    guard: Guard | None = None,
    already_approved: bool = False,
) -> tuple[list[StoredObject], AuditRow]:
    """Apply a named action. This is the only write path besides Funnel seed load."""
    try:
        spec = store.ontology.action_type(action_type)
    except KeyError as exc:
        raise ActionError(f"unknown action type {action_type!r}") from exc

    resolved: dict[str, StoredObject] = {}
    scalars: dict[str, Any] = {}
    for param in spec.parameters:
        raw = parameters.get(param.api_name)
        if param.type == "object":
            try:
                ref = ObjectRef.model_validate(raw)
            except ValidationError as exc:
                raise ActionError(
                    f"parameter {param.api_name} must be an object reference "
                    "{'type': ..., 'id': ...}"
                ) from exc
            if param.object_type and ref.type != param.object_type:
                raise ActionError(
                    f"parameter {param.api_name} expects a {param.object_type} reference, "
                    f"got {ref.type}"
                )
            obj = store.get_object(ref.type, ref.id)
            if obj is None:
                raise ActionError(f"missing {ref.type}:{ref.id}")
            resolved[param.api_name] = obj
        else:
            if raw is None:
                raise ActionError(f"missing parameter {param.api_name}")
            scalars[param.api_name] = _coerce_scalar(param, raw)

    recorded = dict(parameters)
    targets = list(resolved.values())
    if guard is not None:
        try:
            guard.can_act(actor, action_type, targets)
        except SecurityError as exc:
            raise ActionError(str(exc)) from exc

    if spec.approval_required and channel == "mcp" and not already_approved:
        pending_id = store.enqueue_action(action_type, actor, parameters)
        audit = store.append_audit(
            action_type, actor, {**recorded, "pending_id": pending_id}, "pending_approval"
        )
        _trace_parked_action(store, pending_id, action_type, actor, parameters, spec)
        return [], audit

    match channel:
        case "human":
            pass
        case "mcp":
            if spec.mcp_requires_recommendation:
                target = resolved[spec.parameters[0].api_name]
                try:
                    premise = asserted_recommendation(store, action_type, target, fact_id)
                except PolicyError as exc:
                    raise ActionError(str(exc)) from exc
                recorded["fact_id"] = premise.id
            elif not spec.unattended:
                if guard is None or not guard.mcp_unattended_allowed(actor, action_type):
                    pending_id = store.enqueue_action(action_type, actor, parameters)
                    audit = store.append_audit(
                        action_type,
                        actor,
                        {**recorded, "pending_id": pending_id},
                        "pending_approval",
                    )
                    _trace_parked_action(store, pending_id, action_type, actor, parameters, spec)
                    return [], audit
        case _ as unreachable:
            raise TypeError(f"unhandled action channel: {unreachable}")

    edited: list[StoredObject] = []
    try:
        for created in spec.creates:
            raw_id = scalars.get(created.id_parameter) or parameters.get(created.id_parameter)
            if raw_id is None and created.id_parameter in resolved:
                raw_id = resolved[created.id_parameter].id
            if raw_id is None:
                raise ActionError(f"create {created.object_type} missing id")
            props = dict(created.set)
            type_def = store.ontology.object_type(created.object_type)
            props[type_def.primary_key] = str(raw_id)
            updated = store.upsert_object(created.object_type, props, source="action")
            store.mark_overlay(created.object_type, updated.id, list(created.set))
            edited.append(updated)
        for edit in spec.edits:
            current = resolved[edit.parameter]
            if edit.delete:
                store.delete_object(current.object_type, current.id)
                continue
            merged = dict(current.properties)
            merged.update(edit.set)
            updated = store.upsert_object(current.object_type, merged, source="action")
            store.mark_overlay(current.object_type, updated.id, list(edit.set))
            resolved[edit.parameter] = updated
            edited.append(updated)
        audit = store.append_audit(action_type, actor, recorded, "applied")
    except Exception:
        store.append_audit(action_type, actor, recorded, "failed")
        raise
    _fire_target(store, action_type, parameters, audit, actor)
    return edited, audit


def _fire_target(
    store: ObjectStore,
    action_type: str,
    parameters: dict[str, Any],
    audit: AuditRow,
    actor: str,
) -> None:
    """Fire a registered write-back target for this action, if one exists.

    Failures are recorded in the audit log but never undo the local apply — the
    ontology is the system of record; the write-back is a side effect. A failed
    dispatch is surfaced as a separate audit row so a human can retry.
    """
    target = store.get_action_target(action_type)
    if target is None or not target.enabled:
        return
    try:
        result = dispatch(store, target, action_type, parameters, audit)
        store.append_audit(
            "write_back",
            actor,
            {"action_type": action_type, "audit_id": audit.id, "result": result},
            "applied",
        )
    except DispatchError as exc:
        store.append_audit(
            "write_back",
            actor,
            {"action_type": action_type, "audit_id": audit.id, "error": str(exc)},
            "failed",
        )
