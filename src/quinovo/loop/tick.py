"""Unattended ontology loop: synthesize rules, infer, apply recommended actions."""

from __future__ import annotations

import logging
from typing import Any

from quinovo.actions.apply import ActionError
from quinovo.engine.payloads import proposal_payload
from quinovo.llm.author import author_from_index
from quinovo.topics import organize_topics

logger = logging.getLogger(__name__)


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

    semantics: dict[str, Any] = {"conversations": 0, "facts": [], "memories": [], "persons": []}
    try:
        from quinovo.semantic import enrich_new_conversations

        semantics = enrich_new_conversations(kernel, actor)
    except Exception as exc:  # noqa: BLE001 — loop must not die on enrichment
        logger.warning("semantic enrichment failed: %s", exc)
        semantics = {"conversations": 0, "facts": [], "memories": [], "persons": [],
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
    }
