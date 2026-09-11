"""Propose inference rules from the live index. Humans validate via HITL.

Heuristic proposals are pattern-spotting, not understanding, so they never
reach the auto-apply threshold: the strongest heuristic parks at 0.75 and a
human approves it. Only the language model (which reads the evidence) may
propose at 0.8 and above.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from typing import Any

from quinovo.ai.runtime import ProposalKernel, submit_proposal
from quinovo.engine.store import Proposal

DEFAULT_SYNTH_CONFIDENCE = 0.55
STRONG_SYNTH_CONFIDENCE = 0.75
STRONG_N = 3
MIN_PREFIX_SUPPORT = 3
STATUS_LIKE = frozenset({"status", "state", "phase", "lifecycle"})
_SLUG = re.compile(r"[^a-zA-Z0-9_]+")
_NAMESPACE_PREFIX = re.compile(r"^([a-z][a-z]{2,}[:\-_])")
_HEXISH = re.compile(r"^[0-9a-f]{6,}$")


def informative(payload: dict[str, Any]) -> bool:
    """False for rules that only restate a property or link as a fact."""
    if payload.get("kind") != "property_fact":
        return True
    when = payload.get("when_property") or {}
    then = payload.get("then_fact") or {}
    same_predicate = str(then.get("predicate") or "") == str(when.get("api_name") or "")
    same_value = str(then.get("value") or "") == str(when.get("equals") or "")
    return not (same_predicate and same_value)


def namespace_prefix(object_id: str, type_names: frozenset[str] = frozenset()) -> str | None:
    """'principle:P1' -> 'principle:'; 'sem-4375ab' -> None (hash, not a namespace).

    Ids that tag their own type ('fact_s:1_1' on a Fact) or embed a turn id
    are capture bookkeeping, not a namespace anyone would write a rule about.
    """
    match = _NAMESPACE_PREFIX.match(object_id)
    if not match:
        return None
    prefix = match.group(1)
    rest = object_id[len(prefix) :]
    if not rest or _HEXISH.match(rest.lower()) or ":" in rest:
        return None
    if prefix[:-1] in type_names:
        return None
    return prefix


def _slug(*parts: str) -> str:
    raw = "_".join(parts)
    cleaned = _SLUG.sub("_", raw).strip("_")
    return (cleaned or "synth")[:80]


def _confidence(n: int) -> float:
    return STRONG_SYNTH_CONFIDENCE if n >= STRONG_N else DEFAULT_SYNTH_CONFIDENCE


def _rule_fingerprint(payload: dict[str, Any]) -> tuple[Any, ...]:
    kind = payload["kind"]
    source = payload["source_type"]
    match kind:
        case "property_fact":
            when = payload["when_property"]
            return ("property_fact", source, when["api_name"], str(when["equals"]))
        case "forecast_fact":
            when = payload["when_forecast"]
            return ("forecast_fact", source, when["metric"])
        case "fact_link_fact":
            when = payload["when_fact"]
            then = payload["then_fact"]
            return (
                "fact_link_fact",
                source,
                when["predicate"],
                payload.get("when_link"),
                then.get("value"),
            )
        case "join_links":
            return ("join_links", source, tuple(sorted(payload.get("when_links") or [])))
        case "prefix_link":
            then = payload["then_link"]
            return (
                "prefix_link",
                source,
                payload.get("when_pk_prefix"),
                then.get("link_type"),
                then.get("to_id"),
            )
        case "age_fact":
            when = payload["when_age"]
            then = payload["then_fact"]
            return ("age_fact", source, when["property"], then.get("predicate"))
        case _ as unreachable:
            raise TypeError(f"unhandled rule kind: {unreachable}")


def _known_fingerprints(kernel: ProposalKernel) -> set[tuple[Any, ...]]:
    found: set[tuple[Any, ...]] = set()
    ruleset = getattr(kernel, "ruleset", None)
    if ruleset is not None:
        for rule in ruleset.rules:
            try:
                found.add(_rule_fingerprint(rule.model_dump()))
            except (KeyError, TypeError, ValueError):
                continue
    for proposal in kernel.store.list_proposals():
        if proposal.kind != "inference_rule":
            continue
        try:
            found.add(_rule_fingerprint(proposal.payload))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _already_covered(known: set[tuple[Any, ...]], payload: dict[str, Any]) -> bool:
    fingerprint = _rule_fingerprint(payload)
    if fingerprint in known:
        return True
    kind = payload["kind"]
    source = payload["source_type"]
    if kind == "fact_link_fact":
        action = payload["then_fact"]["value"]
        for existing in known:
            if existing[0] == "fact_link_fact" and existing[1] == source and existing[-1] == action:
                return True
    if kind == "join_links":
        for existing in known:
            if existing[0] == "join_links" and existing[1] == source:
                return True
    return False


def _status_props(type_def: Any) -> list[str]:
    names: list[str] = []
    for prop in type_def.properties:
        if prop.api_name in STATUS_LIKE or prop.api_name.endswith("_status"):
            names.append(prop.api_name)
    return names


def _outbound_sides(kernel: ProposalKernel, object_type: str) -> list[str]:
    sides: list[str] = []
    seen: set[str] = set()
    for link in kernel.store.ontology.link_types:
        if link.from_type != object_type:
            continue
        if link.from_name in seen:
            continue
        seen.add(link.from_name)
        sides.append(link.from_name)
    return sides


def candidate_rules(kernel: ProposalKernel) -> Iterator[tuple[float, dict[str, Any]]]:
    ontology = kernel.store.ontology
    for type_def in ontology.object_types:
        objects = kernel.store.list_objects(type_def.api_name)
        # Status-like properties are already facts; restating status=open as an
        # inferred fact says nothing new, so no property_fact rules come from here.

        metrics: Counter[str] = Counter()
        for obj in objects:
            for forecast in kernel.store.list_forecasts(type_def.api_name, obj.id):
                metrics[forecast.metric] += 1
            for metric in kernel.store.list_series_metrics(type_def.api_name, obj.id):
                metrics[metric] += 1
        for metric, n in metrics.items():
            yield _confidence(n), {
                "api_name": _slug("synth_forecast", type_def.api_name, metric),
                "kind": "forecast_fact",
                    "description": f"If {metric} on {type_def.api_name} is at least 0.25, infer at_risk.",
                    "reason": (
                        f"{n} {type_def.api_name} object(s) already have a {metric} "
                        "series or forecast, so Quinovo wants a rule that flags at_risk."
                    ),
                    "source_type": type_def.api_name,
                "confidence_from": "forecast",
                "when_forecast": {"metric": metric, "point_gte": 0.25},
                "then_fact": {"predicate": "at_risk", "value": "true"},
            }

        sides = _outbound_sides(kernel, type_def.api_name)
        linked = 0
        if len(sides) >= 2:
            for obj in objects:
                if all(
                    kernel.store.search_around(type_def.api_name, obj.id, side)
                    for side in sides[:2]
                ):
                    linked += 1
        if len(sides) >= 2 and linked >= 1:
            yield _confidence(linked), {
                "api_name": _slug("synth_join", type_def.api_name),
                "kind": "join_links",
                    "description": f"{type_def.api_name} with {', '.join(sides[:2])} is a complete story.",
                    "reason": (
                        f"{linked} {type_def.api_name} object(s) already have "
                        f"{' and '.join(sides[:2])}, so Quinovo wants a complete-story rule."
                    ),
                    "source_type": type_def.api_name,
                "confidence": 0.9,
                "when_links": sides[:2],
                "then_fact": {"predicate": "story", "value": "complete"},
            }

        at_risk_evidence = bool(metrics) or any(
            fact.predicate == "at_risk"
            for fact in kernel.store.list_inferred_facts(type_def.api_name, None, status=None)
        )
        for action in ontology.action_types:
            if not at_risk_evidence:
                break
            if action.approval_required:
                continue
            if not action.unattended and not action.mcp_requires_recommendation:
                continue
            if not action.parameters or action.parameters[0].object_type != type_def.api_name:
                continue
            for side in sides:
                yield _confidence(max(len(objects), 1)), {
                    "api_name": _slug("synth_recommend", action.api_name, side),
                    "kind": "fact_link_fact",
                    "description": (
                        f"If {type_def.api_name} is at_risk and has {side}, "
                        f"recommend {action.api_name}."
                    ),
                    "reason": (
                        f"The pack already has {action.api_name} for {type_def.api_name}, "
                        f"so Quinovo wants to recommend it when the object is at_risk and has {side}."
                    ),
                    "source_type": type_def.api_name,
                    "confidence": 0.9,
                    "when_fact": {"predicate": "at_risk", "equals": "true"},
                    "when_link": side,
                    "then_fact": {"predicate": "recommended_action", "value": action.api_name},
                }

    buckets: dict[tuple[str, str, str, str], Counter[str]] = defaultdict(Counter)
    type_names = frozenset(item.api_name.lower() for item in ontology.object_types)
    for link in kernel.store.list_all_links():
        if link.from_type in {"Conversation", "Topic"}:
            continue
        prefix = namespace_prefix(link.from_id, type_names)
        if prefix is None:
            continue
        buckets[(link.link_type, link.from_type, prefix, link.to_type)][link.to_id] += 1
    for (link_type, from_type, prefix, to_type), counts in buckets.items():
        to_id, n = counts.most_common(1)[0]
        total = sum(counts.values())
        if n < MIN_PREFIX_SUPPORT or n * 5 < total * 4:
            # Needs real support and a clear majority; a namespace that fans out
            # to many targets is not a rule, it is a coincidence.
            continue
        yield _confidence(n), {
            "api_name": _slug("synth_prefix", from_type, prefix, link_type),
            "kind": "prefix_link",
            "description": f"{from_type} ids starting {prefix} share {link_type} {to_type}:{to_id}.",
            "reason": (
                f"{n} {from_type} objects whose ids start with {prefix} already "
                f"share {link_type} to {to_type} {to_id}."
            ),
            "source_type": from_type,
            "confidence": 0.9,
            "when_pk_prefix": prefix,
            "then_link": {"link_type": link_type, "to_type": to_type, "to_id": to_id},
        }


def synthesize_and_propose(
    kernel: ProposalKernel,
    actor: str = "quinovo-synth",
) -> list[Proposal]:
    """Park synthesized rules for HITL. Heuristics never reach the auto-apply threshold."""
    known = _known_fingerprints(kernel)
    submitted: list[Proposal] = []
    for confidence, payload in candidate_rules(kernel):
        try:
            if not informative(payload) or _already_covered(known, payload):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        confidence = min(confidence, STRONG_SYNTH_CONFIDENCE)
        proposal, _edited = submit_proposal(kernel, "inference_rule", payload, confidence, actor)
        submitted.append(proposal)
        try:
            known.add(_rule_fingerprint(payload))
        except (KeyError, TypeError, ValueError):
            pass
    return submitted
