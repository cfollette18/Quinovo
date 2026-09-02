from __future__ import annotations

from typing import Any

from quinovo.ai.runtime import forecast_actionable
from quinovo.engine.store import Forecast, InferredFact, ObjectStore, Proposal, StoredObject


def forecast_payload(store: ObjectStore, forecast: Forecast) -> dict[str, Any]:
    return {
        "id": forecast.id,
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
    return {
        "type": obj.object_type,
        "id": obj.primary_key,
        "version": obj.version,
        "properties": obj.properties,
        "predictions": [
            forecast_payload(store, item)
            for item in store.list_forecasts(obj.object_type, obj.primary_key)
        ],
        "inferred": [
            inferred_payload(item)
            for item in store.list_inferred_facts(obj.object_type, obj.primary_key)
        ],
    }


def proposal_payload(proposal: Proposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "payload": proposal.payload,
        "confidence": proposal.confidence,
        "status": proposal.status,
        "actor": proposal.actor,
        "created_at": proposal.created_at,
        "resolved_at": proposal.resolved_at,
        "resolved_by": proposal.resolved_by,
    }
