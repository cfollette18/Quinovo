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
from quinovo.loop.tick import tick_digest

DEFAULT_PAGE = 50
MAX_PAGE = 200


def _page(limit: int) -> int:
    return max(1, min(int(limit or DEFAULT_PAGE), MAX_PAGE))


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
            "Quinovo is the agent's operational memory: a typed graph of Topics, "
            "Entities (people, systems, tools, projects), Facts as subject-"
            "predicate-value triples linked to their Entities, plus Decisions, "
            "Todos, OpenQuestions, Memories, and Skills - all filed under Topics. "
            "You are already connected; use it without being asked.\n"
            "Start of session: call briefing once. It is one page - active "
            "topics, open and stale work, recent decisions, memories, top "
            "entities, and what waits on a human.\n"
            "Before answering about any system, person, project, or topic: call "
            "about(name). Before saying you do not know something: call "
            "recall(query). Both return human sentences, not tables.\n"
            "End of every turn: call save_turn with the topic, a one-paragraph "
            "summary, and every fact (subject, predicate, value), decision, todo, "
            "question, memory, and skill from the turn. Add about=[entity names] "
            "on todos, decisions, questions, and memories so they attach to the "
            "graph. If you only have raw text, call remember(text, topic) and the "
            "loop extracts entities and triples itself. Never skip capture. "
            "Missing topics are created; nested topics use slashes "
            "(cretex/workflows) or parent=. Cretex work files under 'cretex' with "
            "subtopics 'technology' and 'workflows'.\n"
            "A background loop already ticks every few seconds and on every "
            "write: it pulls sources, extracts from new turns, infers, and "
            "applies unattended actions. Do not call tick unless you need fresh "
            "results synchronously, and never ask the user to run it.\n"
            "Humans never write packs or rules. Propose with a confidence score: "
            f"below {threshold} parks for approval, {threshold} and above applies. "
            "The only human jobs are approve_proposal, reject_proposal, "
            "approve_inferred_fact, approve_pending_action, reject_pending_action. "
            "Prefer apply_action when a named verb exists. Never SQL. Never YAML. "
            "Every list tool is paged (limit=) - narrow with filters instead of "
            "raising the limit.\n"
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
            "Run one pass of the loop now: pull sources, extract from new turns, "
            "author proposals, infer, apply unattended actions. Returns a short "
            "digest (counts, a few names, what waits on a human). The background "
            "loop already runs this every few seconds; call it only when you "
            "need fresh results synchronously. verbose=true returns everything."
        )
    )
    def tick(actor: str = "autonomous", verbose: bool = False) -> dict[str, Any]:
        result = kernel.tick(actor)
        return result if verbose else tick_digest(result)

    @mcp.tool(
        description=(
            "Start here. One page of what is live right now: active topics with "
            "item counts, open and stale todos, open questions, recent decisions, "
            "memories, the most-connected entities, the last few turns, and what "
            "is waiting on a human. Call this at the start of every session "
            "instead of listing objects."
        )
    )
    def briefing(limit: int = 10) -> dict[str, Any]:
        return kernel.briefing(limit=limit)

    @mcp.tool(
        description=(
            "Everything the graph knows about one thing, as sentences. Pass an "
            "Entity name or alias (Langfuse, Epicor, cfollette18) or a Topic id "
            "(cretex, quinovo). Returns facts about it, facts that point at it, "
            "related entities, todos/decisions/questions/memories that concern "
            "it, and the turns that mentioned it. Call this before answering a "
            "question about a system, person, project, or topic."
        )
    )
    def about(name: str, limit: int = 20) -> dict[str, Any]:
        return kernel.about(name, limit=limit)

    @mcp.tool(
        description=(
            "Ranked search across every object type - facts, decisions, todos, "
            "memories, entities, turns. Each hit is one human line with its "
            "type, id, and topic. Scope with topic= (e.g. cretex) or types= "
            "(e.g. ['Decision','Todo']). Use this before saying 'I don't know'."
        )
    )
    def recall(
        query: str,
        topic: str | None = None,
        types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        return kernel.recall(query, topic=topic, types=types, limit=limit)

    @mcp.tool(
        description=(
            "Capture one agent turn. Writes the Conversation, creates the Topic "
            "if missing, and writes each item as its own linked object. "
            "facts=[{subject, predicate, value}] become triples linked to their "
            "subject and object Entities (the subject Entity is created if new). "
            "todos/decisions/questions/memories accept about=[entity names] so "
            "they hang off the graph. decisions=[{choice, context, reasoning}], "
            "todos=[{text}], questions=[{text}], memories=[{text, kind}], "
            "skills=[{name, description, trigger, path}]. Call this at the end "
            "of every turn. Nested topics use slashes (cretex/workflows) or "
            "parent=. Optional project= groups items under a Project."
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

    @mcp.tool(
        description=(
            "Objects of one type, paged. Narrow with property_name+equals "
            "(exact) or contains= (substring across id and text). Returns "
            "total so you know what you did not see. Prefer recall/about for "
            "questions; use this for exact listings."
        )
    )
    def filter_objects(
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
        contains: str | None = None,
        limit: int = DEFAULT_PAGE,
    ) -> dict[str, Any]:
        return kernel.filter_objects(
            object_type, property_name, equals, contains=contains, limit=_page(limit)
        )

    @mcp.tool(
        description=(
            "Named links, paged. Narrow with link_type=, from_id=, to_id=. "
            "For one object's neighbours use search_around instead."
        )
    )
    def list_links(
        link_type: str | None = None,
        from_id: str | None = None,
        to_id: str | None = None,
        limit: int = DEFAULT_PAGE,
    ) -> dict[str, Any]:
        return kernel.list_links(
            link_type=link_type, from_id=from_id, to_id=to_id, limit=_page(limit)
        )

    @mcp.tool(
        description=(
            "Inferred facts, newest last, paged. status=pending is the HITL "
            "queue. Narrow by object_type and id."
        )
    )
    def list_inferred_facts(
        object_type: str | None = None,
        id: str | None = None,
        status: str | None = "asserted",
        limit: int = DEFAULT_PAGE,
    ) -> dict[str, Any]:
        return kernel.list_inferred_facts(object_type, id, status, limit=_page(limit))

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

    @mcp.tool(description="Pack/rule/type proposals, newest last, paged. Pending items are HITL.")
    def list_proposals(status: str | None = "pending", limit: int = DEFAULT_PAGE) -> dict[str, Any]:
        return kernel.list_proposals(status, limit=_page(limit))

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

    @mcp.tool(
        description=(
            "Typed graph slice: nodes and links. Scope it - types=['Entity','Fact'] "
            "keeps those types, around_type+around_id keeps one node and its "
            "neighbours, limit caps nodes (links follow). Unscoped calls are "
            "capped at limit; use about(name) for a readable view."
        )
    )
    def graph(
        types: list[str] | None = None,
        around_type: str | None = None,
        around_id: str | None = None,
        limit: int = MAX_PAGE,
    ) -> dict[str, Any]:
        around = (around_type, around_id) if around_type and around_id else None
        return kernel.graph(types=types, around=around, limit=_page(limit))

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
