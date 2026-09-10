"""Quinovo as MCP: generated tools over the ontology kernel."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from quinovo.actions.apply import ActionError
from quinovo.ai.runtime import ProposalError
from quinovo.capture import save_turn as capture_turn
from quinovo.kernel import Kernel
from quinovo.llm.tracing import load_langfuse_env
from quinovo.loop.runner import start_autonomy


def create_mcp(kernel: Kernel) -> FastMCP:
    types = ", ".join(item.api_name for item in kernel.ontology.object_types)
    actions = ", ".join(item.api_name for item in kernel.ontology.action_types)
    sides = sorted(
        {link.from_name for link in kernel.ontology.link_types}
        | {link.to_name for link in kernel.ontology.link_types}
    )
    side_hint = ", ".join(sides) if sides else "none in this pack"
    pack_name = kernel.ontology.ontology.api_name
    threshold = kernel.ontology.ontology.auto_apply_min_confidence
    mcp = FastMCP(
        "quinovo",
        instructions=(
            "Quinovo is the operational ontology. You are already connected. "
            "Do not wait for the user to tell you to use it. "
            "Quinovo runs itself: a background loop ticks every few seconds "
            "and on every write — it pulls sources, enriches new turns with "
            "semantic connections, proposes packs/rules, infers, and applies "
            "unattended actions. Never ask the user to say 'quinovo tick' and "
            "never wait to be told to use Quinovo. "
            "At the end of every turn, call remember with the raw turn text "
            "(plus topic when you know it). remember extracts the entities "
            "and relations — who did what to whom, what contains what, what "
            "that implies — and writes linked Facts, Memories, and Persons in "
            "one call. Use save_turn only when you already have structured "
            "facts, decisions, todos, questions, memories, or skills. "
            "Never skip the end-of-turn capture. Missing topics are created. "
            "Cretex work files under topic 'cretex' with subtopics 'technology' and "
            "'workflows' (use topic='cretex/workflows' or parent='cretex'). "
            "tick pulls data sources (including agent transcripts), runs external logic, "
            "synthesizes pack and inference-rule proposals from the live index, infers, "
            "and applies unattended recommended actions. "
            "Humans never write packs or rules. Propose them with a confidence score. "
            f"Below {threshold} parks for HITL; {threshold} and above auto-applies. "
            "The only human job is approve_proposal, reject_proposal, "
            "approve_inferred_fact, approve_pending_action, and reject_pending_action. "
            "Prefer apply_action when a named verb exists. Never SQL. Never write YAML. "
            f"Pack: {pack_name}. Object types: {types}. Link sides: {side_hint}. "
            f"Actions: {actions}."
        ),
    )
    _register_tools(mcp, kernel, side_hint)
    return mcp


def contract_registry() -> FastMCP:
    """The tool surface without a loaded pack, so mcp/contract.py derives from it."""
    mcp = FastMCP("quinovo")
    _register_tools(mcp, None, "defined by the loaded pack")  # type: ignore[arg-type]
    return mcp


def _register_tools(mcp: FastMCP, kernel: Kernel, side_hint: str) -> None:
    @mcp.tool(
        description=(
            "Autonomous loop: pull sources, enrich new turns with semantic "
            "connections, synthesize rules, infer, apply unattended actions, "
            "return HITL. The background loop already runs this — call it only "
            "when you need fresh results synchronously."
        )
    )
    def tick(actor: str = "autonomous") -> dict[str, Any]:
        return kernel.tick(actor)

    @mcp.tool(
        description=(
            "Capture one agent turn as a structured Conversation. Writes the "
            "Conversation, creates the Topic if missing, links it, writes each "
            "structured item (facts, decisions, todos, open questions, memories, "
            "skills) as its own object, and links them back. Call this at the "
            "end of every turn. Nested topics use slashes (cretex/workflows) "
            "or parent=. Optional project= groups facts/todos/decisions under "
            "a Project. Each list argument can be [] or omitted."
        )
    )
    def save_turn(
        session_id: str,
        turn_index: int,
        topic: str,
        summary: str,
        role: str = "",
        parent: str = "",
        project: str = "",
        facts: Any = None,
        decisions: Any = None,
        todos: Any = None,
        questions: Any = None,
        memories: Any = None,
        skills: Any = None,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        return capture_turn(
            kernel,
            session_id,
            turn_index,
            topic,
            summary,
            role=role,
            parent=parent,
            project=project,
            facts=facts,
            decisions=decisions,
            todos=todos,
            questions=questions,
            memories=memories,
            skills=skills,
            actor=actor,
        )

    @mcp.tool(
        description=(
            "Capture raw agent context in one call: pass the turn text and an "
            "optional topic, and Quinovo writes the Conversation plus the "
            "semantic connections a human would see (who did what to whom, "
            "what contains what, what each thing is, what that implies) as "
            "linked Facts, Memories, and Persons. Prefer this over save_turn "
            "unless you already have structured items. Safe to call every "
            "turn without being asked; the background loop enriches the rest."
        )
    )
    def remember(
        text: str,
        topic: str = "quinovo",
        session_id: str = "autonomous",
        role: str = "observed",
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        if kernel is None:  # pragma: no cover — contract registry has no kernel
            raise ValueError("no pack loaded")
        return kernel.remember(
            text, topic=topic, session_id=session_id, role=role, actor=actor
        )

    @mcp.tool(description="List object types in the loaded pack.")
    def list_object_types() -> dict[str, Any]:
        return kernel.list_object_types()

    @mcp.tool(description="Load one object by type and id, including inferred facts.")
    def get_object(object_type: str, id: str) -> dict[str, Any]:
        return kernel.get_object(object_type, id)

    @mcp.tool(description=f"Walk a named link side. In this pack: {side_hint}.")
    def search_around(object_type: str, id: str, side: str) -> dict[str, Any]:
        return kernel.search_around(object_type, id, side)

    @mcp.tool(description="Object-set read: list objects of a type, optionally by property equals.")
    def filter_objects(
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> dict[str, Any]:
        return kernel.filter_objects(object_type, property_name, equals)

    @mcp.tool(description="List every named link in the index.")
    def list_links() -> dict[str, Any]:
        return kernel.list_links()

    @mcp.tool(description="List inferred facts. Pending facts are HITL.")
    def list_inferred_facts(
        object_type: str | None = None,
        id: str | None = None,
        status: str | None = "asserted",
    ) -> dict[str, Any]:
        return kernel.list_inferred_facts(object_type, id, status)

    @mcp.tool(description="Forward-chain typed inference over objects, links, and forecasts.")
    def run_inference() -> dict[str, Any]:
        return kernel.run_inference()

    @mcp.tool(description="Provenance for an inferred fact.")
    def explain_fact(fact_id: int) -> dict[str, Any]:
        return kernel.explain_fact(fact_id)

    @mcp.tool(description="List named actions.")
    def list_actions() -> dict[str, Any]:
        return kernel.list_actions()

    @mcp.tool(description="Apply a named action from the loaded pack.")
    def apply_action(
        action_type: str,
        parameters: dict[str, Any],
        actor: str = "mcp-agent",
        fact_id: int | None = None,
    ) -> dict[str, Any]:
        return kernel.apply_action(
            action_type,
            parameters,
            actor,
            channel="mcp",
            fact_id=fact_id,
        )

    @mcp.tool(description="Read a time-series window on an object metric.")
    def get_series(object_type: str, id: str, metric: str) -> dict[str, Any]:
        return kernel.get_series(object_type, id, metric)

    @mcp.tool(description="Append a time-series point on an object metric.")
    def append_series(object_type: str, id: str, metric: str, ts: str, value: float) -> dict[str, Any]:
        kernel.append_series(object_type, id, metric, ts, value)
        return kernel.get_series(object_type, id, metric)

    @mcp.tool(description="Create or replace an object by type and properties.")
    def upsert_object(object_type: str, properties: dict[str, Any], actor: str = "mcp-agent") -> dict[str, Any]:
        return kernel.upsert_object(object_type, properties, actor)

    @mcp.tool(description="Delete an object and its links.")
    def delete_object(object_type: str, id: str, actor: str = "mcp-agent") -> dict[str, Any]:
        return kernel.delete_object(object_type, id, actor)

    @mcp.tool(description="Create a named link. Types come from the link definition.")
    def set_link(link_type: str, from_id: str, to_id: str, actor: str = "mcp-agent") -> dict[str, Any]:
        return kernel.set_link(link_type, from_id, to_id, actor)

    @mcp.tool(description="Delete a named link.")
    def remove_link(link_type: str, from_id: str, to_id: str, actor: str = "mcp-agent") -> dict[str, Any]:
        return kernel.remove_link(link_type, from_id, to_id, actor)

    @mcp.tool(description="Read the loaded pack YAML documents.")
    def read_pack() -> dict[str, Any]:
        return kernel.read_pack()

    @mcp.tool(description="Propose a pack, rule, type, link, action, or classification. HITL below the pack threshold.")
    def propose(
        kind: str,
        payload: dict[str, Any],
        confidence: float,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        try:
            return kernel.propose(kind, payload, confidence, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Propose a new pack directory. HITL below the pack threshold; humans only approve.")
    def propose_pack(
        dest: str,
        spec: dict[str, Any],
        confidence: float,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        try:
            return kernel.propose("pack", {"dest": dest, "spec": spec}, confidence, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Propose an inference rule for the loaded pack. HITL below the pack threshold.")
    def propose_rule(
        rule: dict[str, Any],
        confidence: float,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        try:
            return kernel.propose("inference_rule", rule, confidence, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Propose an object type for the loaded pack. HITL below the pack threshold.")
    def propose_type(
        type_def: dict[str, Any],
        confidence: float,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        try:
            return kernel.propose("type_definition", type_def, confidence, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Reload pack YAML into the running kernel.")
    def reload() -> dict[str, Any]:
        kernel.reload()
        return {"pack": kernel.ontology.ontology.api_name, "ok": True}

    @mcp.tool(description="Assert a pending inferred fact (HITL).")
    def approve_inferred_fact(fact_id: int, actor: str = "human") -> dict[str, Any]:
        return kernel.approve_inferred_fact(fact_id, actor)

    @mcp.tool(description="Queued actions waiting on approval.")
    def list_pending_actions() -> dict[str, Any]:
        return kernel.list_pending_actions()

    @mcp.tool(description="Approve and apply a queued action.")
    def approve_pending_action(pending_id: int, actor: str = "human") -> dict[str, Any]:
        return kernel.approve_pending_action(pending_id, actor)

    @mcp.tool(description="Reject a queued action.")
    def reject_pending_action(pending_id: int, actor: str = "human") -> dict[str, Any]:
        try:
            return kernel.reject_pending_action(pending_id, actor)
        except (KeyError, ActionError) as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="List pack/rule/type proposals. Pending items are HITL.")
    def list_proposals(status: str | None = "pending") -> dict[str, Any]:
        return kernel.list_proposals(status)

    @mcp.tool(description="Approve a pending proposal and write it to the pack.")
    def approve_proposal(proposal_id: int, actor: str = "human") -> dict[str, Any]:
        try:
            return kernel.approve_proposal(proposal_id, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Reject a pending proposal.")
    def reject_proposal(proposal_id: int, actor: str = "human") -> dict[str, Any]:
        try:
            return kernel.reject_proposal(proposal_id, actor)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Typed graph: objects and named links for the loaded pack.")
    def graph() -> dict[str, Any]:
        return kernel.graph()

    @mcp.tool(description="List registered data sources (connectors that pull data into the ontology).")
    def list_sources() -> dict[str, Any]:
        return kernel.list_sources()

    @mcp.tool(description="Register a data source (kind: http|json|csv|webhook|sql|mcp|synthetic|transcripts). Data flows in through MCP-style connectors.")
    def register_source(
        name: str,
        kind: str,
        object_type: str,
        config: dict[str, Any],
        auto: bool = False,
        description: str = "",
    ) -> dict[str, Any]:
        try:
            return kernel.register_source(
                name, kind, object_type, config, auto=auto, description=description
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Pull one data source by name; upserts its rows as ontology objects.")
    def pull_source(name: str, actor: str = "mcp-agent") -> dict[str, Any]:
        try:
            return kernel.pull_source(name, actor)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Pull every source marked auto.")
    def pull_sources(actor: str = "autonomous") -> dict[str, Any]:
        return kernel.pull_all_sources(actor)

    @mcp.tool(description="Remove a registered data source.")
    def delete_source(name: str) -> dict[str, Any]:
        return kernel.delete_source(name)

    @mcp.tool(description="Push rows into a named source (inbound webhook). Same mapping as pull.")
    def ingest_source(
        name: str,
        payload: dict[str, Any] | list[Any],
        token: str = "",
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        try:
            return kernel.ingest_source(name, payload, token=token or None, actor=actor)
        except (KeyError, ValueError, PermissionError) as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="List external logic sources (functions/endpoints that produce inferred facts).")
    def list_logic_sources() -> dict[str, Any]:
        return kernel.list_logic_sources()

    @mcp.tool(description="Register an external logic source (kind: http). Logic can live anywhere.")
    def register_logic_source(
        name: str,
        kind: str,
        config: dict[str, Any],
        auto: bool = False,
        description: str = "",
    ) -> dict[str, Any]:
        try:
            return kernel.register_logic_source(name, kind, config, auto=auto, description=description)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Run one external logic source; writes its facts/forecasts into the ontology.")
    def run_logic_source(name: str, actor: str = "quinovo-logic") -> dict[str, Any]:
        try:
            return kernel.run_logic_source(name, actor)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Run every logic source marked auto.")
    def run_logic(actor: str = "autonomous") -> dict[str, Any]:
        return kernel.run_all_logic(actor)

    @mcp.tool(description="Remove a registered logic source.")
    def delete_logic_source(name: str) -> dict[str, Any]:
        return kernel.delete_logic_source(name)

    @mcp.tool(description="List write-back targets bound to actions (webhook, slack, email, mcp, sql).")
    def list_action_targets() -> dict[str, Any]:
        return kernel.list_action_targets()

    @mcp.tool(description="Bind a write-back target to an action so applying it drives a real change in an external system.")
    def register_action_target(
        action_type: str,
        kind: str,
        config: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        try:
            return kernel.register_action_target(action_type, kind, config, description=description)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="Remove an action write-back target.")
    def delete_action_target(action_type: str) -> dict[str, Any]:
        return kernel.delete_action_target(action_type)

    @mcp.tool(description="Reason over the ontology and propose applying a named action. HITL below the pack threshold.")
    def propose_action(
        action_type: str,
        parameters: dict[str, Any],
        confidence: float,
        actor: str = "quinovo-ai",
        reason: str = "",
    ) -> dict[str, Any]:
        try:
            return kernel.propose_action(action_type, parameters, confidence, actor, reason)
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(description="The SDK surface: tool contract for MCP, Hermes, and ADK clients.")
    def contract() -> dict[str, Any]:
        return kernel.tool_contract()


def run_stdio(kernel: Kernel) -> None:
    load_langfuse_env()
    start_autonomy(kernel)
    kernel.nudge()
    create_mcp(kernel).run(transport="stdio")
