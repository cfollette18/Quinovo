from __future__ import annotations

from typing import Any

from quinovo.engine.store import AuditRow, ObjectStore, StoredObject
from quinovo.language.models import ActionParameterDef
from quinovo.policy import ActionChannel, PolicyError, asserted_recommendation
from quinovo.security import Guard, SecurityError


class ActionError(Exception):
    """Action rejected: unknown type, bad params, missing object, or policy."""


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
            if not isinstance(raw, dict) or "id" not in raw:
                raise ActionError(
                    f"parameter {param.api_name} must be an object reference {{'id': ...}}"
                )
            obj = store.get_object(param.object_type or "", str(raw["id"]))
            if obj is None:
                raise ActionError(f"missing {param.object_type}:{raw['id']}")
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
                    return [], audit
        case _ as unreachable:
            raise TypeError(f"unhandled action channel: {unreachable}")

    edited: list[StoredObject] = []
    try:
        for created in spec.creates:
            raw_id = scalars.get(created.id_parameter) or parameters.get(created.id_parameter)
            if raw_id is None and created.id_parameter in resolved:
                raw_id = resolved[created.id_parameter].primary_key
            if raw_id is None:
                raise ActionError(f"create {created.object_type} missing id")
            props = dict(created.set)
            type_def = store.ontology.object_type(created.object_type)
            props[type_def.primary_key] = str(raw_id)
            updated = store.upsert_object(created.object_type, props, source="action")
            store.mark_overlay(created.object_type, updated.primary_key, list(created.set))
            edited.append(updated)
        for edit in spec.edits:
            current = resolved[edit.parameter]
            if edit.delete:
                store.delete_object(current.object_type, current.primary_key)
                continue
            merged = dict(current.properties)
            merged.update(edit.set)
            updated = store.upsert_object(current.object_type, merged, source="action")
            store.mark_overlay(current.object_type, updated.primary_key, list(edit.set))
            resolved[edit.parameter] = updated
            edited.append(updated)
        audit = store.append_audit(action_type, actor, recorded, "applied")
    except Exception:
        store.append_audit(action_type, actor, recorded, "failed")
        raise
    return edited, audit
