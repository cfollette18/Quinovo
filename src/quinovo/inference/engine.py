"""Typed inference over objects, links, and forecasts — not a generic graph query."""

from __future__ import annotations

from quinovo.engine.store import InferredFact, ObjectStore, StoredObject
from quinovo.inference.rules import InferenceRule, InferenceRuleset
from quinovo.policy import requires_hitl


def run_inference(
    store: ObjectStore,
    ruleset: InferenceRuleset,
    passes: int = 3,
) -> list[InferredFact]:
    """
    Forward-chain pack rules. Conclusions are inferred facts with provenance.
    Below 80% confidence they stay pending (HITL); otherwise they are asserted.
    """
    produced: list[InferredFact] = []
    for _ in range(passes):
        wave: list[InferredFact] = []
        for rule in ruleset.rules:
            for fact in _fire_rule(store, rule):
                if fact is not None:
                    wave.append(fact)
        if not wave:
            break
        produced.extend(wave)
    return produced


def approve_inferred_fact(
    store: ObjectStore,
    fact_id: int,
    actor: str,
    ruleset: InferenceRuleset | None = None,
) -> InferredFact:
    fact = store.get_inferred_fact(fact_id)
    if fact is None:
        raise KeyError(fact_id)
    if fact.status != "pending":
        raise ValueError(f"fact {fact_id} is {fact.status}, not pending")
    updated = store.set_inferred_fact_status(fact_id, "asserted")
    store.append_audit(
        "approve_inference",
        actor,
        {"fact_id": fact_id, "rule": fact.rule},
        "applied",
    )
    if ruleset is not None:
        run_inference(store, ruleset)
    return updated


def _fire_rule(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    match rule.kind:
        case "forecast_fact":
            return _forecast_fact(store, rule)
        case "fact_link_fact":
            return _fact_link_fact(store, rule)
        case "prefix_link":
            return _prefix_link(store, rule)
        case "property_fact":
            return _property_fact(store, rule)
        case "join_links":
            return _join_links(store, rule)
        case _ as unreachable:
            raise TypeError(f"unhandled rule kind: {unreachable}")


def _forecast_fact(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    when = rule.when_forecast
    then = rule.then_fact
    if when is None or then is None:
        return []
    out: list[InferredFact] = []
    for obj in store.list_objects(rule.source_type):
        forecast = store.latest_forecast(obj.object_type, obj.primary_key, when.metric)
        if forecast is None or forecast.point < when.point_gte:
            continue
        confidence = forecast.confidence if rule.confidence == "forecast" else float(rule.confidence)
        fact = _commit_fact(
            store,
            obj,
            then.predicate,
            then.value,
            confidence,
            rule.api_name,
            "predicted",
            {"forecast_metric": when.metric, "forecast_point": forecast.point},
        )
        if fact is not None:
            out.append(fact)
    return out


def _fact_link_fact(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    when = rule.when_fact
    then = rule.then_fact
    side = rule.when_link
    if when is None or then is None or side is None:
        return []
    out: list[InferredFact] = []
    for obj in store.list_objects(rule.source_type):
        if not _has_asserted_fact(store, obj, when.predicate, when.equals):
            continue
        neighbors = store.search_around(obj.object_type, obj.primary_key, side)
        if not neighbors:
            continue
        confidence = float(rule.confidence) if rule.confidence != "forecast" else 0.9
        joined = ",".join(f"{n.object_type}:{n.primary_key}" for n in neighbors)
        fact = _commit_fact(
            store,
            obj,
            then.predicate,
            f"{then.value}:{joined}",
            confidence,
            rule.api_name,
            "inferred",
            {"link": side, "neighbors": joined, "from_fact": when.predicate},
        )
        if fact is not None:
            out.append(fact)
    return out


def _prefix_link(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    prefix = rule.when_pk_prefix
    then = rule.then_link
    if prefix is None or then is None:
        return []
    out: list[InferredFact] = []
    confidence = float(rule.confidence) if rule.confidence != "forecast" else 0.9
    for obj in store.list_objects(rule.source_type):
        if not obj.primary_key.startswith(prefix):
            continue
        already = store.has_link(
            then.link_type,
            obj.object_type,
            obj.primary_key,
            then.to_type,
            then.to_id,
        )
        fact = _commit_fact(
            store,
            obj,
            f"link:{then.link_type}",
            f"{then.to_type}:{then.to_id}",
            confidence,
            rule.api_name,
            "inferred",
            {"when_pk_prefix": prefix},
        )
        if fact is None:
            continue
        if fact.status == "asserted" and not already:
            store.add_link(
                then.link_type,
                obj.object_type,
                obj.primary_key,
                then.to_type,
                then.to_id,
            )
        out.append(fact)
    return out


def _property_fact(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    when = rule.when_property
    then = rule.then_fact
    if when is None or then is None:
        return []
    out: list[InferredFact] = []
    confidence = float(rule.confidence) if rule.confidence != "forecast" else 0.9
    for obj in store.list_objects(rule.source_type):
        if str(obj.properties.get(when.api_name)) != when.equals:
            continue
        fact = _commit_fact(
            store,
            obj,
            then.predicate,
            then.value,
            confidence,
            rule.api_name,
            "inferred",
            {"property": when.api_name, "equals": when.equals},
        )
        if fact is not None:
            out.append(fact)
    return out


def _join_links(store: ObjectStore, rule: InferenceRule) -> list[InferredFact]:
    then = rule.then_fact
    if then is None:
        return []
    out: list[InferredFact] = []
    confidence = float(rule.confidence) if rule.confidence != "forecast" else 0.9
    for obj in store.list_objects(rule.source_type):
        hops: list[str] = []
        missing = False
        for side in rule.when_links:
            neighbors = store.search_around(obj.object_type, obj.primary_key, side)
            if not neighbors:
                missing = True
                break
            hops.append(
                f"{side}=" + ",".join(f"{n.object_type}:{n.primary_key}" for n in neighbors)
            )
        if missing:
            continue
        fact = _commit_fact(
            store,
            obj,
            then.predicate,
            then.value,
            confidence,
            rule.api_name,
            "inferred",
            {"joins": hops},
        )
        if fact is not None:
            out.append(fact)
    return out


def _has_asserted_fact(
    store: ObjectStore,
    obj: StoredObject,
    predicate: str,
    value: str,
) -> bool:
    for fact in store.list_inferred_facts(obj.object_type, obj.primary_key, status="asserted"):
        if fact.predicate == predicate and fact.value == value:
            return True
    return False


def _commit_fact(
    store: ObjectStore,
    obj: StoredObject,
    predicate: str,
    value: str,
    confidence: float,
    rule: str,
    provenance: str,
    provenance_detail: dict | None = None,
) -> InferredFact | None:
    threshold = store.ontology.ontology.auto_apply_min_confidence
    status = "pending" if requires_hitl(confidence, threshold) else "asserted"
    previous = [
        f
        for f in store.list_inferred_facts(obj.object_type, obj.primary_key)
        if f.predicate == predicate and f.rule == rule
    ]
    if previous and previous[0].value == value and previous[0].status == status:
        return None
    if previous and previous[0].status == "asserted" and status == "pending":
        return None
    fact = store.upsert_inferred_fact(
        obj.object_type,
        obj.primary_key,
        predicate,
        value,
        confidence,
        rule,
        provenance,
        status,
        provenance_detail=provenance_detail,
    )
    store.append_audit(
        "infer",
        "quinovo-reasoner",
        {
            "fact_id": fact.id,
            "rule": rule,
            "confidence": confidence,
            "status": status,
        },
        status,
    )
    return fact
