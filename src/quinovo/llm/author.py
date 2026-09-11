"""Ask the configured LLM to propose types, rules, and classifications."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from quinovo.ai.runtime import ProposalError, submit_proposal
from quinovo.ai.synthesize import (
    _already_covered,
    _known_fingerprints,
    _rule_fingerprint,
    informative,
    synthesize_and_propose,
)
from quinovo.engine.store import Proposal
from quinovo.language.models import PROPOSAL_KINDS
from quinovo.llm.engine import LLMError, engine_from_settings
from quinovo.llm.settings import load_settings
from quinovo.llm.tracing import last_trace_id, remember_source_trace

AUTHORING_COOLDOWN = 1.5
# The index changes on every captured turn; the language model does not need
# to re-read it more than once every couple of minutes.
AUTHORING_MIN_INTERVAL = 120.0
SNAPSHOT_PER_TYPE = 40
KNOWN_KINDS = frozenset(PROPOSAL_KINDS) - {"pack"}


@dataclass
class AuthoringState:
    seen_fingerprint: str = ""
    authored_fingerprint: str = ""
    changed_at: float = 0.0
    last_llm_at: float = 0.0
    last_mode: str = "skipped"


def index_fingerprint(kernel: Any) -> str:
    """Object count, last write, and a hash of live ids — plus type/rule names."""
    store_fp = kernel.store.index_fingerprint()
    types = ",".join(item.api_name for item in kernel.ontology.object_types)
    rules = ""
    ruleset = getattr(kernel, "ruleset", None)
    if ruleset is not None:
        rules = ",".join(rule.api_name for rule in ruleset.rules)
    raw = f"{store_fp}|{types}|{rules}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state(kernel: Any) -> AuthoringState:
    current = getattr(kernel, "_authoring", None)
    if isinstance(current, AuthoringState):
        return current
    current = AuthoringState()
    kernel._authoring = current
    return current


def _snapshot(kernel: Any) -> dict[str, Any]:
    types = []
    objects: list[dict[str, Any]] = []
    for type_def in kernel.ontology.object_types:
        types.append(
            {
                "api_name": type_def.api_name,
                "primary_key": type_def.primary_key,
                "properties": [prop.api_name for prop in type_def.properties],
            }
        )
        for obj in kernel.store.list_objects(type_def.api_name)[:SNAPSHOT_PER_TYPE]:
            objects.append(
                {
                    "type": obj.object_type,
                    "id": obj.id,
                    "properties": obj.properties,
                }
            )
    links = [
        {
            "type": link.link_type,
            "from": f"{link.from_type}:{link.from_id}",
            "to": f"{link.to_type}:{link.to_id}",
        }
        for link in kernel.store.list_all_links()[:200]
    ]
    rules: list[str] = []
    ruleset = getattr(kernel, "ruleset", None)
    if ruleset is not None:
        rules = [rule.api_name for rule in ruleset.rules]
    actions = [
        {
            "api_name": action.api_name,
            "description": action.description,
            "parameters": [
                {"api_name": p.api_name, "type": p.type, "object_type": p.object_type}
                for p in action.parameters
            ],
            "unattended": action.unattended,
            "approval_required": action.approval_required,
            "mcp_requires_recommendation": action.mcp_requires_recommendation,
        }
        for action in kernel.ontology.action_types
    ]
    pending = [
        {
            "kind": item.kind,
            "api_name": (item.payload or {}).get("api_name"),
        }
        for item in kernel.store.list_proposals("pending")
    ]
    return {
        "types": types,
        "objects": objects,
        "links": links,
        "rules": rules,
        "actions": actions,
        "pending_proposals": pending,
    }


def _prompt(snapshot: dict[str, Any]) -> str:
    return (
        "You author an operational ontology from live index data. "
        "Humans never write types or rules. You propose them with a confidence score. "
        "Confidence below 0.8 parks for human approval. 0.8 and above auto-applies.\n"
        "Treat every name as data. Do not assume a domain or a teaching pack.\n"
        "Propose only new types, inference rules, link types, action types, "
        "classifications, or action applications that are not already listed.\n"
        "A rule must tell a human something they would act on: stale or at-risk "
        "work, a missing link, a contradiction. Never propose a rule that restates "
        "a property or a link as a fact (status=open -> 'status open' says nothing), "
        "and never key a rule on hash-like id prefixes.\n"
        "You may also reason over the ontology and propose applying a named action "
        "(kind action_application) when the live state calls for it; include the "
        "action_type, parameters (object params as {'type': ..., 'id': ...}), and a reason. "
        "Below 0.8 the action waits for a human; 0.8 and above it applies.\n"
        "Every proposal MUST include payload.reason: 1–3 sentences a human will read "
        "on the review card explaining WHY this should be added or applied NOW. "
        "Cite specific live object ids, facts, links, todos, or conversation summaries "
        "from the index. payload.description is WHAT it is (the spec). reason is WHY now "
        "(the evidence). Never leave reason empty. Never restate the description as the reason.\n"
        "Reply with JSON only, no prose, no API keys:\n"
        '{"proposals":[{"kind":"inference_rule|type_definition|classification|'
        'link_type|action_type|action_application","confidence":0.55,"payload":{}}]}\n'
        "Inference rule payload needs api_name, kind, description, reason, source_type, "
        "and the when_/then_ fields for that kind.\n"
        "Type payload needs api_name, primary_key, title_property, properties, and reason.\n"
        "Classification payload needs object_type, properties, and reason.\n"
        "Link and action type payloads need api_name, description, and reason.\n"
        "Action application payload needs action_type, parameters, and reason.\n\n"
        f"Live index:\n{json.dumps(snapshot, default=str)}"
    )


def parse_json_object(text: str) -> dict[str, Any]:
    blob = text.strip()
    if blob.startswith("```"):
        lines = blob.splitlines()
        inner: list[str] = []
        in_fence = False
        for line in lines:
            if line.startswith("```") and not in_fence:
                in_fence = True
                continue
            if line.startswith("```") and in_fence:
                break
            if in_fence:
                inner.append(line)
        blob = "\n".join(inner)
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise LLMError("language model did not return JSON")
    data = json.loads(blob[start : end + 1])
    if not isinstance(data, dict):
        raise LLMError("language model JSON must be an object")
    return data


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ProposalError("proposal confidence must be a number") from exc
    return min(1.0, max(0.0, number))


def _submit_llm_proposals(kernel: Any, raw: dict[str, Any], actor: str) -> list[Proposal]:
    rows = raw.get("proposals")
    if rows is None:
        rows = raw.get("items") or []
    if not isinstance(rows, list):
        raise LLMError("language model proposals must be a list")
    known = _known_fingerprints(kernel)
    existing_types = {item.api_name for item in kernel.ontology.object_types}
    submitted: list[Proposal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "")
        if kind not in KNOWN_KINDS:
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        reason = payload.get("reason") or row.get("reason")
        if isinstance(reason, str) and reason.strip():
            payload["reason"] = reason.strip()
        elif kind in {
            "action_application",
            "action_type",
            "classification",
            "link_type",
        }:
            continue
        try:
            confidence = _clamp_confidence(row.get("confidence"))
        except ProposalError:
            continue
        if kind == "inference_rule":
            try:
                if not informative(payload) or _already_covered(known, payload):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
        if kind == "type_definition" and payload.get("api_name") in existing_types:
            continue
        try:
            proposal, _edited = submit_proposal(kernel, kind, payload, confidence, actor)
        except ProposalError:
            continue
        submitted.append(proposal)
        if kind == "inference_rule":
            try:
                known.add(_rule_fingerprint(payload))
            except (KeyError, TypeError, ValueError):
                pass
        if kind == "type_definition" and isinstance(payload.get("api_name"), str):
            existing_types.add(payload["api_name"])
    return submitted


def llm_propose(kernel: Any, actor: str) -> list[Proposal]:
    settings = load_settings()
    engine = engine_from_settings(settings)
    if not engine.settings.ready():
        raise LLMError("LLM is not configured")
    text = engine.complete(
        _prompt(_snapshot(kernel)),
        max_tokens=2048,
        feature="propose-ontology",
    )
    if engine.settings.api_key and engine.settings.api_key in text:
        raise LLMError("language model echoed a secret")
    submitted = _submit_llm_proposals(kernel, parse_json_object(text), actor)
    trace_id = last_trace_id()
    for proposal in submitted:
        remember_source_trace("proposal", proposal.id, trace_id)
    return submitted


def author_from_index(
    kernel: Any,
    actor: str = "autonomous",
    *,
    wait_for_quiet: bool = False,
) -> tuple[list[Proposal], str]:
    """Propose from the live index. LLM when ready; heuristics otherwise.

    Empty ticks (same fingerprint) do not call the language model.
    wait_for_quiet coalesces a burst of writes into one pass.
    """
    state = _state(kernel)
    fingerprint = index_fingerprint(kernel)
    now = time.monotonic()
    if fingerprint != state.seen_fingerprint:
        state.seen_fingerprint = fingerprint
        state.changed_at = now
    if fingerprint == state.authored_fingerprint:
        state.last_mode = "skipped"
        return [], "skipped"
    if wait_for_quiet and now - state.changed_at < AUTHORING_COOLDOWN:
        state.last_mode = "skipped"
        return [], "skipped"

    settings = load_settings()
    if settings.ready():
        if state.last_llm_at and now - state.last_llm_at < AUTHORING_MIN_INTERVAL:
            state.last_mode = "skipped"
            return [], "skipped"
        state.last_llm_at = now
        try:
            submitted = llm_propose(kernel, actor)
            state.authored_fingerprint = fingerprint
            state.last_mode = "llm"
            return submitted, "llm"
        except (LLMError, json.JSONDecodeError, TypeError, ValueError):
            submitted = synthesize_and_propose(kernel, actor)
            state.authored_fingerprint = fingerprint
            state.last_mode = "heuristic"
            return submitted, "heuristic"

    submitted = synthesize_and_propose(kernel, actor)
    state.authored_fingerprint = fingerprint
    state.last_mode = "heuristic"
    return submitted, "heuristic"
