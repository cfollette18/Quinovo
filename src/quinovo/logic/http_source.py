"""HTTP logic source: POST the ontology snapshot to an endpoint, get facts back.

The endpoint receives a small snapshot of the object type it cares about and
returns {"facts": [...], "forecasts": [...]}. Each fact/forecast is written into
the ontology. This is the "logic lives anywhere" pattern: an external model,
optimizer, or rule service becomes a Quinovo logic source over HTTP.
"""

from __future__ import annotations

from typing import Any

import httpx

from quinovo.engine.store import ObjectStore
from quinovo.logic.base import LogicError, LogicResult, SourceRecord


class HttpLogicSource:
    """Call an HTTP endpoint that returns inferred facts and/or forecasts.

    config:
        url: str                — endpoint URL.
        object_type: str         — optional; snapshot objects of this type to send.
        snapshot_limit: int     — optional, default 200.
        rule: str                — rule name to attribute facts to (default: source name).
        headers: dict            — optional request headers. Never logged.
    """

    kind = "http"

    def run(self, store: ObjectStore, record: SourceRecord) -> LogicResult:
        url = record.config.get("url")
        if not isinstance(url, str) or not url:
            raise LogicError("http logic source needs config.url")
        object_type = record.config.get("object_type")
        snapshot_limit = int(record.config.get("snapshot_limit") or 200)
        headers = record.config.get("headers") or {}
        if not isinstance(headers, dict):
            raise LogicError("http logic source headers must be a mapping")
        rule = record.config.get("rule") or record.name
        snapshot = _snapshot(store, object_type, snapshot_limit)
        try:
            response = httpx.post(url, json=snapshot, headers=headers, timeout=20.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise LogicError(f"http logic source call failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise LogicError("http logic source must return a JSON object")
        return _ingest(store, payload, rule, record.name)


def _snapshot(store: ObjectStore, object_type: str | None, limit: int) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    types: list[str] = []
    if object_type:
        try:
            store.ontology.object_type(object_type)
            types = [object_type]
        except KeyError:
            types = []
    else:
        types = [t.api_name for t in store.ontology.object_types]
    for name in types:
        for obj in store.list_objects(name)[:limit]:
            objects.append(
                {"type": obj.object_type, "id": obj.id, "properties": obj.properties}
            )
    return {"objects": objects}


def _ingest(
    store: ObjectStore, payload: dict[str, Any], rule: str, source_name: str
) -> LogicResult:
    facts_in = payload.get("facts") or []
    forecasts_in = payload.get("forecasts") or []
    facts: list[dict[str, Any]] = []
    forecasts: list[dict[str, Any]] = []
    if not isinstance(facts_in, list):
        raise LogicError("http logic source facts must be a list")
    if not isinstance(forecasts_in, list):
        raise LogicError("http logic source forecasts must be a list")
    for item in facts_in:
        if not isinstance(item, dict):
            continue
        obj_type = item.get("object_type")
        pk = item.get("id") or item.get("pk")
        predicate = item.get("predicate")
        value = item.get("value")
        confidence = float(item.get("confidence", 0.9))
        if not (obj_type and pk and predicate and value is not None):
            continue
        fact = store.upsert_inferred_fact(
            str(obj_type),
            str(pk),
            str(predicate),
            str(value),
            confidence,
            str(item.get("rule") or rule),
            f"logic:{source_name}",
            "asserted",
            {"source": source_name, **{k: v for k, v in item.items() if k not in (
                "object_type", "id", "pk", "predicate", "value", "confidence", "rule"
            )}},
        )
        facts.append({"id": fact.id, "predicate": fact.predicate, "value": fact.value})
    for item in forecasts_in:
        if not isinstance(item, dict):
            continue
        obj_type = item.get("object_type")
        pk = item.get("id") or item.get("pk")
        metric = item.get("metric")
        if not (obj_type and pk and metric):
            continue
        forecast = store.put_forecast(
            str(obj_type),
            str(pk),
            str(metric),
            float(item.get("horizon_hours", 24)),
            float(item.get("point", 0.0)),
            str(item.get("model", source_name)),
            float(item.get("confidence", 0.9)),
            q10=item.get("q10"),
            q90=item.get("q90"),
        )
        forecasts.append({"id": forecast.id, "metric": forecast.metric})
    return LogicResult(facts=facts, forecasts=forecasts, detail=f"{len(facts)} facts, {len(forecasts)} forecasts")
