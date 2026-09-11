"""Unattended ontology loop: synthesize rules, infer, apply recommended actions."""

from __future__ import annotations

import logging
from typing import Any

from quinovo.actions.apply import ActionError
from quinovo.engine.payloads import proposal_payload
from quinovo.llm.author import author_from_index
from quinovo.llm.eval_dataset import collect_eval_failures
from quinovo.semantic import enrich_new_conversations
from quinovo.topics import organize_topics

logger = logging.getLogger(__name__)

DIGEST_ITEMS = 5


def _first(items: list[Any], key: str, n: int = DIGEST_ITEMS) -> list[Any]:
    return [item.get(key) if isinstance(item, dict) else item for item in items[:n]]


def tick_digest(result: dict[str, Any]) -> dict[str, Any]:
    """The tick result an agent can read in one glance: counts plus a few names.

    The full result stays available to the HTTP app and tests; over MCP a
    200 KB dump of every pending fact was the single worst thing Quinovo did.
    """
    semantics = result.get("semantics") or {}
    pending_facts = result.get("pending_facts") or []
    pending_actions = result.get("pending_actions") or []
    pending_proposals = result.get("pending_proposals") or []
    applied = result.get("applied") or []
    errors = result.get("errors") or []
    return {
        "authoring": result.get("authoring"),
        "inferred": len(result.get("facts") or []),
        "applied": len(applied),
        "errors": len(errors),
        "enriched_turns": int(semantics.get("conversations") or 0),
        "turns_remaining": int(semantics.get("remaining") or 0),
        "new_entities": _first(list(semantics.get("entities") or []), "name"),
        "new_facts": len(semantics.get("facts") or []),
        "sources_pulled": len(result.get("sources_pulled") or []),
        "topics_created": list(result.get("topics_created") or [])[:DIGEST_ITEMS],
        "waiting_on_human": {
            "inferred_facts": len(pending_facts),
            "actions": len(pending_actions),
            "proposals": len(pending_proposals),
        },
        "next_for_human": [
            *[
                f"fact #{f.get('id')}: {f.get('object_type')} {f.get('object_id')} {f.get('predicate')}={f.get('value')}"
                for f in pending_facts[:DIGEST_ITEMS]
            ],
            *[
                f"proposal #{p.get('id')}: {p.get('title') or p.get('kind')}"
                for p in pending_proposals[:DIGEST_ITEMS]
            ],
            *[
                f"action #{a.get('id')}: {a.get('action_type')}"
                for a in pending_actions[:DIGEST_ITEMS]
            ],
        ],
        "first_errors": [e.get("error") for e in errors[:DIGEST_ITEMS]],
    }


def tick(
    kernel: Any,
    actor: str = "autonomous",
    *,
    wait_for_quiet: bool = False,
) -> dict[str, Any]:
    """One pass of the operational loop. No human prompt required.

    1. Pull data sources marked auto (data flows in through MCP-style connectors).
    2. Run external logic sources marked auto (logic can live anywhere).
    3. Group similar objects into Topic baskets (and nest subtopics).
    4. Enrich new Conversations with semantic connections (who did what to
       whom, what contains what, what that implies) — no agent call needed.
    5. Author pack/rule proposals from the live index (LLM if connected).
    6. Forward-chain inference if the pack has rules.
    7. Apply asserted recommended_action verbs that are unattended
       (or MCP-gated only by that recommendation).
    8. Return pending HITL for a human — that is the only stop.
    """
    pulled: list[dict[str, Any]] = []
    if hasattr(kernel, "pull_all_sources"):
        try:
            pulled = kernel.pull_all_sources(actor).get("pulled", [])
        except Exception as exc:  # noqa: BLE001 — loop must not die on a bad source
            logger.warning("source pull failed: %s", exc)
            pulled = [{"error": "source pull failed"}]

    logic_ran: list[dict[str, Any]] = []
    if hasattr(kernel, "run_all_logic"):
        try:
            logic_ran = kernel.run_all_logic(actor).get("ran", [])
        except Exception as exc:  # noqa: BLE001 — loop must not die on a bad logic source
            logger.warning("logic run failed: %s", exc)
            logic_ran = [{"error": "logic run failed"}]

    topics: dict[str, Any] = {"created": []}
    try:
        topics = organize_topics(kernel, actor)
    except Exception as exc:  # noqa: BLE001 — loop must not die on topic grouping
        logger.warning("topic organize failed: %s", exc)
        topics = {"created": [], "error": "topic organize failed"}

    semantics: dict[str, Any] = {"conversations": 0, "facts": [], "entities": []}
    try:
        semantics = enrich_new_conversations(kernel, actor)
    except Exception as exc:  # noqa: BLE001 — loop must not die on enrichment
        logger.warning("semantic enrichment failed: %s", exc)
        semantics = {"conversations": 0, "facts": [], "entities": [],
                     "error": "semantic enrichment failed"}

    proposed, authoring = author_from_index(
        kernel, actor, wait_for_quiet=wait_for_quiet
    )

    facts: list[dict[str, Any]] = []
    if kernel.ruleset is not None:
        facts = kernel.run_inference()["facts"]

    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    recommendations = [
        fact
        for fact in kernel.store.list_inferred_facts(status="asserted")
        if fact.predicate == "recommended_action"
    ]
    for fact in recommendations:
        action_type = fact.value.split(":", 1)[0]
        try:
            spec = kernel.ontology.action_type(action_type)
        except KeyError:
            errors.append({"fact_id": fact.id, "error": f"unknown action {action_type!r}"})
            continue
        if spec.approval_required:
            continue
        if not spec.unattended and not spec.mcp_requires_recommendation:
            continue
        if not spec.parameters:
            errors.append({"fact_id": fact.id, "error": f"{action_type} has no parameters"})
            continue
        param = spec.parameters[0]
        try:
            result = kernel.apply_action(
                action_type,
                {param.api_name: {"type": fact.object_type, "id": fact.object_id}},
                actor,
                channel="mcp",
                fact_id=fact.id,
            )
            applied.append(result)
        except (ActionError, KeyError, PermissionError, ValueError) as exc:
            errors.append({"fact_id": fact.id, "action_type": action_type, "error": str(exc)})

    pending_facts = kernel.list_inferred_facts(status="pending")["facts"]
    pending_actions = [
        row
        for row in kernel.list_pending_actions()["actions"]
        if row["status"] == "pending"
    ]
    pending_proposals = [
        proposal_payload(item) for item in kernel.store.list_proposals("pending")
    ]
    eval_dataset = collect_eval_failures()
    return {
        "facts": facts,
        "applied": applied,
        "errors": errors,
        "pending_facts": pending_facts,
        "pending_actions": pending_actions,
        "pending_proposals": pending_proposals,
        "proposed": [proposal_payload(item) for item in proposed],
        "authoring": authoring,
        "semantics": semantics,
        "sources_pulled": pulled,
        "logic_ran": logic_ran,
        "topics_created": topics.get("created") or [],
        "eval_dataset": eval_dataset,
    }
