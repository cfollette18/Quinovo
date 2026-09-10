"""The only place store records become JSON. No inline response dicts elsewhere."""

from __future__ import annotations

from typing import Any

from quinovo.ai.runtime import forecast_actionable
from quinovo.apps.humanize import (
    kind_label,
    proposal_target,
    proposal_title,
    proposal_what,
    proposal_why,
)
from quinovo.engine.store import (
    ActionTargetRecord,
    AuditRow,
    Forecast,
    InferredFact,
    LogicSourceRecord,
    ObjectStore,
    PendingAction,
    Proposal,
    SourceRecord,
    SourceRunRecord,
    StoredLink,
    StoredObject,
)
from quinovo.language.models import Ontology


def forecast_payload(store: ObjectStore, forecast: Forecast) -> dict[str, Any]:
    return {
        "id": forecast.id,
        "object_type": forecast.object_type,
        "object_id": forecast.object_id,
        "metric": forecast.metric,
        "horizon_hours": forecast.horizon_hours,
        "point": forecast.point,
        "q10": forecast.q10,
        "q90": forecast.q90,
        "model": forecast.model,
        "confidence": forecast.confidence,
        "as_of": forecast.as_of,
        "actionable": forecast_actionable(store, forecast),
    }


def inferred_payload(fact: InferredFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "object_type": fact.object_type,
        "object_id": fact.object_id,
        "predicate": fact.predicate,
        "value": fact.value,
        "confidence": fact.confidence,
        "rule": fact.rule,
        "provenance": fact.provenance,
        "provenance_detail": fact.provenance_detail,
        "status": fact.status,
        "hitl": fact.status == "pending",
    }


def object_payload(store: ObjectStore, obj: StoredObject) -> dict[str, Any]:
    noticed = [
        inferred_payload(item)
        for item in store.list_inferred_facts(obj.object_type, obj.id)
    ]
    return {
        "type": obj.object_type,
        "id": obj.id,
        "version": obj.version,
        "properties": obj.properties,
        "forecasts": [
            forecast_payload(store, item)
            for item in store.list_forecasts(obj.object_type, obj.id)
        ],
        "facts": noticed,
        "inferred": noticed,
    }


def function_object_payload(obj: StoredObject) -> dict[str, Any]:
    """The lean object shape exposed inside sandboxed pack functions."""
    return {"type": obj.object_type, "id": obj.id, "properties": obj.properties}


def proposal_payload(proposal: Proposal) -> dict[str, Any]:
    payload = proposal.payload or {}
    kind = proposal.kind
    return {
        "id": proposal.id,
        "kind": kind,
        "payload": payload,
        "confidence": proposal.confidence,
        "status": proposal.status,
        "actor": proposal.actor,
        "created_at": proposal.created_at,
        "resolved_at": proposal.resolved_at,
        "resolved_by": proposal.resolved_by,
        "kicker": kind_label(kind),
        "title": proposal_title(kind, payload),
        "why": proposal_why(kind, payload),
        "what": proposal_what(kind, payload),
        "target": proposal_target(kind, payload),
    }


def pending_action_payload(action: PendingAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "action_type": action.action_type,
        "actor": action.actor,
        "parameters": action.parameters,
        "status": action.status,
        "created_at": action.created_at,
        "resolved_at": action.resolved_at,
        "resolved_by": action.resolved_by,
    }


def source_payload(
    source: SourceRecord,
    last_run: SourceRunRecord | None = None,
) -> dict[str, Any]:
    return {
        "name": source.name,
        "kind": source.kind,
        "object_type": source.object_type,
        "config": source.config,
        "auto": source.auto,
        "description": source.description,
        "created_at": source.created_at,
        "enabled": source.enabled,
        "last_run": source_run_payload(last_run) if last_run is not None else None,
    }


def source_run_payload(run: SourceRunRecord) -> dict[str, Any]:
    return {
        "id": run.id,
        "source_name": run.source_name,
        "created_at": run.created_at,
        "upserted": run.upserted,
        "status": run.status,
        "detail": run.detail,
    }


def logic_source_payload(source: LogicSourceRecord) -> dict[str, Any]:
    return {
        "name": source.name,
        "kind": source.kind,
        "config": source.config,
        "auto": source.auto,
        "description": source.description,
        "created_at": source.created_at,
    }


def action_target_payload(
    target: ActionTargetRecord,
    last_dispatch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "action_type": target.action_type,
        "kind": target.kind,
        "config": target.config,
        "description": target.description,
        "created_at": target.created_at,
        "enabled": target.enabled,
        "last_dispatch": last_dispatch,
    }


def audit_payload(row: AuditRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "action_type": row.action_type,
        "actor": row.actor,
        "created_at": row.created_at,
        "parameters": row.parameters,
        "result": row.result,
    }


def link_payload(link: StoredLink) -> dict[str, Any]:
    return {
        "link_type": link.link_type,
        "from_type": link.from_type,
        "from_id": link.from_id,
        "to_type": link.to_type,
        "to_id": link.to_id,
    }


def graph_payload(ontology: Ontology, store: ObjectStore) -> dict[str, Any]:
    """Nodes keyed by the composite Type:id label; links reference those ids."""
    nodes: list[dict[str, Any]] = []
    for type_def in ontology.object_types:
        title_prop = type_def.title_property
        for obj in store.list_objects(type_def.api_name):
            label = obj.properties.get(title_prop, obj.id)
            nodes.append(
                {
                    "id": f"{obj.object_type}:{obj.id}",
                    "type": obj.object_type,
                    "pk": obj.id,
                    "label": str(label),
                }
            )
    links = [
        {
            "link_type": link.link_type,
            "from_id": f"{link.from_type}:{link.from_id}",
            "to_id": f"{link.to_type}:{link.to_id}",
        }
        for link in store.list_all_links()
    ]
    edges = [
        {
            "type": item["link_type"],
            "from": item["from_id"],
            "to": item["to_id"],
        }
        for item in links
    ]
    return {
        "pack": ontology.ontology.api_name,
        "display_name": ontology.ontology.display_name,
        "nodes": nodes,
        "links": links,
        "edges": edges,
    }
