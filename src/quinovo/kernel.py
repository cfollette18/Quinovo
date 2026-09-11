"""Domain-blind ontology kernel. MCP and HTTP both call this."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quinovo.actions.apply import ActionError, apply_action
from quinovo.actions.dispatch import TARGET_KINDS
from quinovo.ai.propose import propose_from_files
from quinovo.ai.runtime import (
    ProposalError,
    submit_proposal,
    write_forecast,
)
from quinovo.ai.runtime import (
    approve_proposal as apply_stored_proposal,
)
from quinovo.ai.runtime import (
    reject_proposal as reject_stored_proposal,
)
from quinovo.apps.humanize import title_case
from quinovo.capture import save_turn as capture_turn
from quinovo.connectors import (
    ConnectorError,
    ConnectorRegistry,
    build_registry,
)
from quinovo.connectors.mapping import extract_rows, upsert_rows
from quinovo.engine.payloads import (
    action_target_payload,
    forecast_payload,
    graph_payload,
    inferred_payload,
    link_payload,
    logic_source_payload,
    object_payload,
    pending_action_payload,
    proposal_payload,
    source_payload,
    source_run_payload,
)
from quinovo.engine.store import ObjectStore
from quinovo.funnel.seed import load_seed
from quinovo.inference.engine import approve_inferred_fact, run_inference
from quinovo.inference.forecasting import forecast_metric
from quinovo.inference.load import load_ruleset
from quinovo.inference.rules import InferenceRuleset
from quinovo.language.load import load_ontology
from quinovo.language.models import Ontology
from quinovo.llm.disagreement import record_user_disagreement
from quinovo.logic import (
    LogicError,
    LogicRegistry,
)
from quinovo.logic import (
    build_registry as build_logic_registry,
)
from quinovo.logic.functions import FunctionError, FunctionManifest, load_functions, run_function
from quinovo.loop.tick import tick as run_tick
from quinovo.pack.authoring import PackCreateError, create_pack, read_pack, write_pack_document
from quinovo.pack.validate import validate_pack
from quinovo.policy import ActionChannel
from quinovo.security import Guard, load_security, seed_tuples
from quinovo.semantic import remember_text
from quinovo.topics import catalog_topics
from quinovo.topics import create_topic as run_create_topic
from quinovo.topics import delete_topic as run_delete_topic
from quinovo.topics import organize_topics as run_organize_topics
from quinovo.topics import update_topic as run_update_topic
from quinovo.train import (
    TrainError,
    create_job,
    list_datasets,
    list_jobs,
    parse_filters,
    preview_data,
    public_dataset,
    public_job,
    save_dataset,
    train_dir_for,
)
from quinovo.workspace import DEFAULT_DB, DEFAULT_PACK, WORLD_PACK


class Kernel:
    def __init__(self, pack_dir: Path, db_path: Path) -> None:
        self.pack_dir = pack_dir
        validate_pack(pack_dir)
        self.ontology: Ontology = load_ontology(pack_dir / "ontology.yaml")
        self.store = ObjectStore(self.ontology, db_path)
        rules_path = pack_dir / "inference.yaml"
        self.ruleset: InferenceRuleset | None = (
            load_ruleset(rules_path) if rules_path.exists() else None
        )
        security_path = pack_dir / "security.yaml"
        self.policy = load_security(security_path) if security_path.exists() else None
        self.guard = Guard(self.store, self.policy)
        if self.policy is not None:
            seed_tuples(self.store, self.policy)
        functions_path = pack_dir / "functions.yaml"
        self.functions: FunctionManifest | None = (
            load_functions(functions_path) if functions_path.exists() else None
        )
        seed = pack_dir / "seed.yaml"
        if seed.exists():
            load_seed(self.store, seed)
        self.store.on_index_change = self.nudge
        self.connectors: ConnectorRegistry = build_registry()
        self.logic: LogicRegistry = build_logic_registry()
        self._ensure_capture_sources()

    def list_object_types(self) -> dict[str, Any]:
        return {
            "object_types": [
                {
                    "api_name": item.api_name,
                    "description": item.description,
                    "primary_key": item.primary_key,
                    "implements": item.implements,
                }
                for item in self.ontology.object_types
            ],
            "interfaces": [item.api_name for item in self.ontology.interfaces],
        }

    def get_object(
        self,
        object_type: str,
        id: str,
        actor: str | None = None,
        scenario: str | None = None,
    ) -> dict[str, Any]:
        obj = self.store.get_object(object_type, id)
        if obj is None:
            raise KeyError(f"missing {object_type}:{id}")
        if actor is not None and self.policy is not None and not self.guard.can_read(actor, obj):
            raise PermissionError(f"{actor} cannot read {object_type}:{id}")
        payload = object_payload(self.store, obj)
        if actor is not None and self.policy is not None:
            payload["properties"] = self.guard.redact(actor, obj)
        if scenario:
            overlay = self.store.scenario_overlay(scenario, object_type, id)
            merged = dict(payload["properties"])
            merged.update(overlay)
            payload["properties"] = merged
            payload["scenario"] = scenario
        return payload

    def search_around(self, object_type: str, id: str, side: str) -> dict[str, Any]:
        if self.store.get_object(object_type, id) is None:
            raise KeyError(f"missing {object_type}:{id}")
        neighbors = self.store.search_around(object_type, id, side)
        return {"objects": [object_payload(self.store, item) for item in neighbors]}

    def filter_objects(
        self,
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        found = self.store.filter_objects(object_type, property_name, equals)
        if actor is not None and self.policy is not None:
            found = [item for item in found if self.guard.can_read(actor, item)]
        return {"objects": [object_payload(self.store, item) for item in found]}

    def list_inferred_facts(
        self,
        object_type: str | None = None,
        id: str | None = None,
        status: str | None = "asserted",
    ) -> dict[str, Any]:
        facts = self.store.list_inferred_facts(object_type, id, status=status)
        return {"facts": [inferred_payload(item) for item in facts]}

    def explain_fact(self, fact_id: int) -> dict[str, Any]:
        fact = self.store.get_inferred_fact(fact_id)
        if fact is None:
            raise KeyError(fact_id)
        payload = inferred_payload(fact)
        payload["why"] = fact.provenance_detail
        return payload

    def run_inference(self) -> dict[str, Any]:
        if self.ruleset is None:
            raise FileNotFoundError("this pack has no inference.yaml")
        facts = run_inference(self.store, self.ruleset)
        return {"facts": [inferred_payload(item) for item in facts]}

    def list_actions(self) -> dict[str, Any]:
        return {
            "actions": [
                {
                    "api_name": action.api_name,
                    "description": action.description,
                    "mcp_requires_recommendation": action.mcp_requires_recommendation,
                    "unattended": action.unattended,
                    "approval_required": action.approval_required,
                    "parameters": [
                        {
                            "api_name": param.api_name,
                            "type": param.type,
                            "object_type": param.object_type,
                        }
                        for param in action.parameters
                    ],
                }
                for action in self.ontology.action_types
            ]
        }

    def apply_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        actor: str = "local",
        *,
        channel: ActionChannel = "human",
        fact_id: int | None = None,
        already_approved: bool = False,
    ) -> dict[str, Any]:
        edited, audit = apply_action(
            self.store,
            action_type,
            parameters,
            actor,
            channel=channel,
            fact_id=fact_id,
            guard=self.guard if self.policy is not None else None,
            already_approved=already_approved,
        )
        result = {
            "audit_id": audit.id,
            "action_type": audit.action_type,
            "actor": audit.actor,
            "created_at": audit.created_at,
            "result": audit.result,
            "parameters": audit.parameters,
            "objects": [object_payload(self.store, item) for item in edited],
        }
        self.nudge()
        return result

    def list_pending_actions(self) -> dict[str, Any]:
        return {
            "actions": [
                pending_action_payload(item) for item in self.store.list_pending_actions()
            ]
        }

    def approve_pending_action(self, pending_id: int, actor: str) -> dict[str, Any]:
        pending = self.store.get_pending_action(pending_id)
        if pending is None:
            raise KeyError(pending_id)
        if pending.status != "pending":
            raise ActionError(f"pending action {pending_id} is {pending.status}, not pending")
        self.store.set_pending_action_status(pending_id, "approved", actor)
        result = self.apply_action(
            pending.action_type,
            pending.parameters,
            actor,
            channel="human",
            already_approved=True,
        )
        if result["result"] == "applied":
            self.store.set_pending_action_status(pending_id, "applied", actor)
        return result

    def reject_pending_action(self, pending_id: int, actor: str) -> dict[str, Any]:
        pending = self.store.get_pending_action(pending_id)
        if pending is None:
            raise KeyError(pending_id)
        if pending.status != "pending":
            raise ActionError(f"pending action {pending_id} is {pending.status}, not pending")
        rejected = self.store.set_pending_action_status(pending_id, "rejected", actor)
        self.store.append_audit(
            "reject_pending_action",
            actor,
            {"pending_id": pending_id, "action_type": pending.action_type},
            "rejected",
        )
        self.nudge()
        public = pending_action_payload(rejected)
        record_user_disagreement(
            disagreement=True,
            source="pending_action",
            source_id=rejected.id,
            actor=actor,
            kind=rejected.action_type,
            title=title_case(rejected.action_type),
            payload=rejected.parameters or {},
        )
        return {"pending_action": public}

    def write_forecast(
        self,
        object_type: str,
        id: str,
        metric: str,
        horizon_hours: float,
        point: float,
        model: str,
        confidence: float,
        q10: float | None = None,
        q90: float | None = None,
    ) -> dict[str, Any]:
        forecast = write_forecast(
            self.store,
            object_type,
            id,
            metric,
            horizon_hours,
            point,
            model,
            confidence,
            q10=q10,
            q90=q90,
        )
        self.nudge()
        return {"forecast": forecast_payload(self.store, forecast)}

    def forecast_from_series(
        self,
        object_type: str,
        id: str,
        metric: str,
        horizon_hours: float,
        model: str = "timesfm-2.5",
        confidence: float = 0.85,
    ) -> dict[str, Any]:
        forecast = forecast_metric(
            self.store, object_type, id, metric, horizon_hours, model, confidence
        )
        self.nudge()
        return {"forecast": forecast_payload(self.store, forecast)}

    def append_series(
        self, object_type: str, id: str, metric: str, ts: str, value: float
    ) -> None:
        self.store.append_series_point(object_type, id, metric, ts, value)
        self.nudge()

    def get_series(self, object_type: str, id: str, metric: str) -> dict[str, Any]:
        points = self.store.series_window(object_type, id, metric)
        return {
            "object_type": object_type,
            "id": id,
            "metric": metric,
            "points": [{"ts": ts, "value": value} for ts, value in points],
        }

    def run_pack_function(self, api_name: str, args: dict[str, Any] | None = None) -> Any:
        if self.functions is None:
            raise FileNotFoundError("this pack has no functions.yaml")
        for spec in self.functions.functions:
            if spec.api_name == api_name:
                return run_function(self.store, self.pack_dir, spec, args or {})
        raise KeyError(api_name)

    def propose_types(self, root: Path, confidence: float, actor: str = "quinovo-proposer") -> list[Any]:
        return propose_from_files(self, root, confidence, actor)

    def propose(
        self,
        kind: str,
        payload: dict[str, Any],
        confidence: float,
        actor: str = "quinovo-ai",
    ) -> dict[str, Any]:
        proposal, edited = submit_proposal(self, kind, payload, confidence, actor)
        result = {
            "proposal": proposal_payload(proposal),
            "hitl": proposal.status == "pending",
            "objects": [object_payload(self.store, item) for item in edited],
        }
        self.nudge()
        return result

    def approve_proposal(self, proposal_id: int, actor: str) -> dict[str, Any]:
        proposal, edited = apply_stored_proposal(self, proposal_id, actor)
        result = {
            "proposal": proposal_payload(proposal),
            "objects": [object_payload(self.store, item) for item in edited],
        }
        self.nudge()
        return result

    def reject_proposal(self, proposal_id: int, actor: str) -> dict[str, Any]:
        proposal = reject_stored_proposal(self, proposal_id, actor)
        public = proposal_payload(proposal)
        record_user_disagreement(
            disagreement=True,
            source="proposal",
            source_id=proposal.id,
            actor=actor,
            kind=proposal.kind,
            title=str(public.get("title") or ""),
            why=str(public.get("why") or ""),
            what=str(public.get("what") or ""),
            confidence=proposal.confidence,
            payload=proposal.payload or {},
        )
        return {"proposal": public}

    def object_view_data(self, object_type: str, id: str) -> dict[str, Any]:
        payload = self.get_object(object_type, id)
        links: dict[str, list[dict[str, Any]]] = {}
        for link in self.ontology.link_types:
            sides: list[str] = []
            if link.from_type == object_type:
                sides.append(link.from_name)
            if link.to_type == object_type:
                sides.append(link.to_name)
            for side in sides:
                neighbors = self.store.search_around(object_type, id, side)
                if neighbors:
                    links[side] = [object_payload(self.store, item) for item in neighbors]
        series = {
            metric: self.get_series(object_type, id, metric)["points"]
            for metric in self.store.list_series_metrics(object_type, id)
        }
        return {
            "object": payload,
            "actions": self.list_actions()["actions"],
            "links": links,
            "series": series,
            "pack_name": self.ontology.ontology.display_name,
        }

    def catalog_data(self) -> dict[str, Any]:
        return {
            "counts": {
                item.api_name: len(self.store.list_objects(item.api_name))
                for item in self.ontology.object_types
            },
            "topics": catalog_topics(self),
        }

    def organize_topics(
        self,
        actor: str = "autonomous",
        *,
        use_llm: bool = False,
    ) -> dict[str, Any]:
        return run_organize_topics(self, actor, use_llm=use_llm)

    def create_topic(
        self,
        name: str,
        description: str = "",
        parent: str = "",
        actor: str = "human",
    ) -> dict[str, Any]:
        return run_create_topic(
            self, name=name, description=description, parent=parent, actor=actor
        )

    def update_topic(
        self,
        topic_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        parent: str | None = None,
        status: str | None = None,
        actor: str = "human",
    ) -> dict[str, Any]:
        return run_update_topic(
            self,
            topic_id,
            name=name,
            description=description,
            parent=parent,
            status=status,
            actor=actor,
        )

    def delete_topic(self, topic_id: str, actor: str = "human") -> dict[str, Any]:
        return run_delete_topic(self, topic_id, actor=actor)

    def inference_queue(self) -> dict[str, Any]:
        pending_actions = [
            pending_action_payload(item)
            for item in self.store.list_pending_actions(status="pending")
        ]
        return {
            "facts": self.list_inferred_facts(status=None)["facts"],
            "proposals": self.list_proposals("pending")["proposals"],
            "pending_actions": pending_actions,
        }

    def train_root(self) -> Path:
        return train_dir_for(self.store.db_path)

    def train_filters(self, **kwargs: Any) -> dict[str, Any]:
        return parse_filters(**kwargs)

    def train_preview(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return preview_data(self.ontology, self.store, filters or parse_filters())

    def save_train_dataset(self, name: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        dataset = save_dataset(
            self.ontology,
            self.store,
            self.train_root(),
            name,
            filters or parse_filters(),
        )
        return public_dataset(dataset)

    def list_train_datasets(self) -> dict[str, Any]:
        return {
            "datasets": [public_dataset(row) for row in list_datasets(self.train_root())]
        }

    def create_train_job(
        self,
        name: str,
        dataset_id: str,
        size_class: str = "small",
    ) -> dict[str, Any]:
        return public_job(
            create_job(
                self.train_root(),
                name=name,
                dataset_id=dataset_id,
                size_class=size_class,
            )
        )

    def list_train_jobs(self) -> dict[str, Any]:
        return {"jobs": [public_job(row) for row in list_jobs(self.train_root())]}

    def llm(self):
        from quinovo.llm.engine import engine_from_settings

        return engine_from_settings()

    def graph(self) -> dict[str, Any]:
        return graph_payload(self.ontology, self.store)

    def approve_inferred_fact(self, fact_id: int, actor: str) -> dict[str, Any]:
        fact = approve_inferred_fact(self.store, fact_id, actor, self.ruleset)
        self.nudge()
        return {"fact": inferred_payload(fact)}

    def reload_seed(self) -> None:
        seed = self.pack_dir / "seed.yaml"
        if not seed.exists():
            raise FileNotFoundError(seed)
        load_seed(self.store, seed)
        self.nudge()

    def reload(self) -> None:
        autonomy = getattr(self, "_autonomy", None)
        if autonomy is not None:
            with autonomy._lock:
                self._reload_unlocked()
            return
        self._reload_unlocked()

    def _reload_unlocked(self) -> None:
        db_path = self.store.db_path
        pack_dir = self.pack_dir
        autonomy = getattr(self, "_autonomy", None)
        last_tick = getattr(self, "_last_tick", None)
        authoring = getattr(self, "_authoring", None)
        connectors = getattr(self, "connectors", None)
        logic = getattr(self, "logic", None)
        self.store.close()
        self.__init__(pack_dir, db_path)
        self._autonomy = autonomy
        self._last_tick = last_tick
        self._authoring = authoring
        if connectors is not None:
            self.connectors = connectors
        if logic is not None:
            self.logic = logic
        self._ensure_capture_sources()

    def nudge(self) -> None:
        from quinovo.loop.runner import nudge

        nudge(self)

    def _ensure_capture_sources(self) -> None:
        """Register the transcript ingest source so tick captures every agent chat.

        Only the live world pack backed by a database under .data gets this
        source. Temporary databases (tests, scratch kernels) stay clean.
        """
        names = {item.api_name for item in self.ontology.object_types}
        if "Conversation" not in names or "Topic" not in names:
            return
        if self.pack_dir.resolve() != WORLD_PACK.resolve():
            return
        try:
            self.store.db_path.resolve().relative_to(DEFAULT_DB.parent.resolve())
        except ValueError:
            return
        home = str(Path.home())
        self.store.upsert_source(
            "cursor-transcripts",
            "transcripts",
            "Conversation",
            {
                "globs": [
                    f"{home}/.cursor/projects/*/agent-transcripts/*/*.jsonl",
                ],
                "default_topic": "quinovo",
                "path_topics": {
                    "cretex-automation": "workflows",
                    "cretex": "cretex",
                    "Quinovo": "quinovo",
                    "quinovo": "quinovo",
                    "jig": "jig",
                    "orzo": "orzo",
                },
            },
            auto=True,
            description="Ingest Cursor agent transcripts as Conversation objects.",
        )

    def save_turn(
        self,
        session_id: str,
        turn_index: int,
        topic: str,
        summary: str,
        *,
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
            self,
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

    def remember(
        self,
        text: str,
        *,
        topic: str = "quinovo",
        session_id: str = "autonomous",
        role: str = "observed",
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        """Capture raw text and enrich it in one call (see quinovo.semantic)."""
        return remember_text(
            self, text, topic=topic, session_id=session_id, role=role, actor=actor
        )

    def read_pack(self) -> dict[str, Any]:
        return read_pack(self.pack_dir)

    def write_pack_document(self, filename: str, document: dict[str, Any]) -> dict[str, Any]:
        path = write_pack_document(self.pack_dir, filename, document)
        self.reload()
        self.nudge()
        return {"path": str(path), "file": filename, "pack": self.ontology.ontology.api_name}

    def upsert_object(self, object_type: str, properties: dict[str, Any], actor: str = "mcp-agent") -> dict[str, Any]:
        obj = self.store.upsert_object(object_type, properties, source="action")
        self.store.mark_overlay(object_type, obj.id, list(properties))
        self.store.append_audit(
            "upsert_object",
            actor,
            {"object_type": object_type, "id": obj.id},
            "applied",
        )
        self.nudge()
        return object_payload(self.store, obj)

    def delete_object(self, object_type: str, id: str, actor: str = "mcp-agent") -> dict[str, Any]:
        if self.store.get_object(object_type, id) is None:
            raise KeyError(f"missing {object_type}:{id}")
        self.store.delete_object(object_type, id)
        self.store.append_audit(
            "delete_object",
            actor,
            {"object_type": object_type, "id": id},
            "applied",
        )
        self.nudge()
        return {"deleted": f"{object_type}:{id}"}

    def set_link(
        self,
        link_type: str,
        from_id: str,
        to_id: str,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        spec = self.ontology.link_type(link_type)
        self.store.add_link(link_type, spec.from_type, from_id, spec.to_type, to_id)
        self.store.append_audit(
            "set_link",
            actor,
            {"link_type": link_type, "from": from_id, "to": to_id},
            "applied",
        )
        self.nudge()
        return {
            "link_type": link_type,
            "from": f"{spec.from_type}:{from_id}",
            "to": f"{spec.to_type}:{to_id}",
        }

    def remove_link(
        self,
        link_type: str,
        from_id: str,
        to_id: str,
        actor: str = "mcp-agent",
    ) -> dict[str, Any]:
        spec = self.ontology.link_type(link_type)
        self.store.remove_link(link_type, spec.from_type, from_id, spec.to_type, to_id)
        self.store.append_audit(
            "remove_link",
            actor,
            {"link_type": link_type, "from": from_id, "to": to_id},
            "applied",
        )
        self.nudge()
        return {
            "removed": True,
            "link_type": link_type,
            "from": f"{spec.from_type}:{from_id}",
            "to": f"{spec.to_type}:{to_id}",
        }

    def list_links(self) -> dict[str, Any]:
        return {"links": [link_payload(link) for link in self.store.list_all_links()]}

    def tick(self, actor: str = "autonomous", *, wait_for_quiet: bool = False) -> dict[str, Any]:
        return run_tick(self, actor, wait_for_quiet=wait_for_quiet)

    def list_proposals(self, status: str | None = "pending") -> dict[str, Any]:
        return {"proposals": [proposal_payload(item) for item in self.store.list_proposals(status)]}

    # --- Data sources (connectors / MCP-as-connector) ------------------

    def register_source(
        self,
        name: str,
        kind: str,
        object_type: str,
        config: dict[str, Any],
        *,
        auto: bool = False,
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Register a data source. Data flows into the ontology through MCP-style connectors."""
        try:
            self.ontology.object_type(object_type)
        except KeyError as exc:
            raise ValueError(f"unknown object type {object_type!r}") from exc
        if kind not in self.connectors.kinds() and kind != "callable":
            raise ValueError(f"unknown source kind {kind!r}; known: {self.connectors.kinds()}")
        return source_payload(
            self.store.upsert_source(name, kind, object_type, config, auto, description, enabled)
        )

    def register_source_callable(self, name: str, object_type: str, fn: Any, **kwargs: Any) -> dict[str, Any]:
        """Register a Python callable as a source (programmatic / agent use)."""
        try:
            self.ontology.object_type(object_type)
        except KeyError as exc:
            raise ValueError(f"unknown object type {object_type!r}") from exc
        self.connectors.register_callable(name, fn)
        return source_payload(
            self.store.upsert_source(
                name,
                "callable",
                object_type,
                kwargs.get("config") or {},
                bool(kwargs.get("auto")),
                kwargs.get("description") or "",
                bool(kwargs.get("enabled", True)),
            )
        )

    def list_sources(self) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for run in self.store.list_source_runs(200):
            latest.setdefault(run.source_name, run)
        return {
            "sources": [
                source_payload(item, latest.get(item.name))
                for item in self.store.list_sources()
            ]
        }

    def set_source_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        record = self.store.get_source(name)
        if record is None:
            raise KeyError(f"unknown source {name!r}")
        return source_payload(
            self.store.upsert_source(
                record.name,
                record.kind,
                record.object_type,
                record.config,
                record.auto,
                record.description,
                enabled,
            )
        )

    def ingest_source(
        self,
        name: str,
        payload: Any,
        *,
        token: str | None = None,
        actor: str = "ingest",
    ) -> dict[str, Any]:
        """Push rows into a named source (inbound webhook). Mapping matches pull."""
        del actor
        record = self.store.get_source(name)
        if record is None:
            raise KeyError(f"unknown source {name!r}")
        if not record.enabled:
            raise ValueError(f"source {name!r} is paused")
        expected = record.config.get("token")
        if isinstance(expected, str) and expected:
            if token != expected:
                raise PermissionError("that source token does not match")
        rows_path = record.config.get("rows_path")
        path = rows_path if isinstance(rows_path, str) and rows_path else None
        rows = extract_rows(payload, path, singleton=True)
        try:
            run = upsert_rows(self.store, record, rows, f"{len(rows)} pushed")
        except ConnectorError as exc:
            self.store.record_source_run(name, 0, status="error", detail=str(exc))
            raise ValueError(str(exc)) from exc
        self.store.record_source_run(name, len(run.upserted), status="ok", detail=run.detail)
        self.nudge()
        return {
            "source": name,
            "upserted": run.upserted,
            "count": len(run.upserted),
            "detail": run.detail,
        }

    def pull_source(self, name: str, actor: str = "mcp-agent", *, wake: bool = True) -> dict[str, Any]:
        del actor
        record = self.store.get_source(name)
        if record is None:
            raise KeyError(f"unknown source {name!r}")
        if not record.enabled:
            raise ValueError(f"source {name!r} is paused")
        prev = self.store.on_index_change
        self.store.on_index_change = None
        try:
            run = self.connectors.pull(self.store, record)
        except ConnectorError as exc:
            self.store.on_index_change = prev
            self.store.record_source_run(name, 0, status="error", detail=str(exc))
            raise ValueError(str(exc)) from exc
        self.store.on_index_change = prev
        self.store.record_source_run(name, len(run.upserted), status="ok", detail=run.detail)
        if wake and run.upserted:
            self.nudge()
        return {
            "source": name,
            "upserted": run.upserted,
            "count": len(run.upserted),
            "detail": run.detail,
        }

    def pull_all_sources(self, actor: str = "autonomous") -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for record in self.store.list_sources():
            if not record.auto or not record.enabled:
                continue
            try:
                results.append(self.pull_source(record.name, actor, wake=False))
            except ValueError as exc:
                results.append({"source": record.name, "error": str(exc)})
        return {"pulled": results}

    def list_source_runs(self, limit: int = 50) -> dict[str, Any]:
        return {"runs": [source_run_payload(run) for run in self.store.list_source_runs(limit)]}

    def delete_source(self, name: str) -> dict[str, Any]:
        self.store.delete_source(name)
        return {"deleted": name}

    # --- External logic sources ----------------------------------------

    def register_logic_source(
        self,
        name: str,
        kind: str,
        config: dict[str, Any],
        *,
        auto: bool = False,
        description: str = "",
    ) -> dict[str, Any]:
        if kind not in self.logic.kinds() and kind != "callable":
            raise ValueError(f"unknown logic kind {kind!r}; known: {self.logic.kinds()}")
        return logic_source_payload(
            self.store.upsert_logic_source(name, kind, config, auto, description)
        )

    def register_logic_callable(self, name: str, fn: Any, **kwargs: Any) -> dict[str, Any]:
        self.logic.register_callable(name, fn)
        return logic_source_payload(
            self.store.upsert_logic_source(
                name, "callable", kwargs.get("config") or {}, bool(kwargs.get("auto")), kwargs.get("description") or ""
            )
        )

    def list_logic_sources(self) -> dict[str, Any]:
        return {
            "logic_sources": [
                logic_source_payload(item) for item in self.store.list_logic_sources()
            ]
        }

    def run_logic_source(self, name: str, actor: str = "quinovo-logic") -> dict[str, Any]:
        record = self.store.get_logic_source(name)
        if record is None:
            raise KeyError(f"unknown logic source {name!r}")
        try:
            result = self.logic.run(self.store, record)
        except LogicError as exc:
            raise ValueError(str(exc)) from exc
        self.store.append_audit(
            "run_logic",
            actor,
            {"source": name, "facts": len(result.facts), "forecasts": len(result.forecasts)},
            "applied",
        )
        self.nudge()
        return {
            "source": name,
            "facts": result.facts,
            "forecasts": result.forecasts,
            "detail": result.detail,
        }

    def run_all_logic(self, actor: str = "autonomous") -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for record in self.store.list_logic_sources():
            if not record.auto:
                continue
            try:
                results.append(self.run_logic_source(record.name, actor))
            except ValueError as exc:
                results.append({"source": record.name, "error": str(exc)})
        return {"ran": results}

    def delete_logic_source(self, name: str) -> dict[str, Any]:
        self.store.delete_logic_source(name)
        return {"deleted": name}

    # --- Action write-back targets -------------------------------------

    def register_action_target(
        self,
        action_type: str,
        kind: str,
        config: dict[str, Any],
        *,
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        try:
            self.ontology.action_type(action_type)
        except KeyError as exc:
            raise ValueError(f"unknown action type {action_type!r}") from exc
        if kind not in TARGET_KINDS:
            raise ValueError(f"unknown target kind {kind!r}; known: {list(TARGET_KINDS)}")
        return action_target_payload(
            self.store.upsert_action_target(action_type, kind, config, description, enabled)
        )

    def set_action_target_enabled(self, action_type: str, enabled: bool) -> dict[str, Any]:
        record = self.store.get_action_target(action_type)
        if record is None:
            raise KeyError(f"unknown action target {action_type!r}")
        return action_target_payload(
            self.store.upsert_action_target(
                record.action_type,
                record.kind,
                record.config,
                record.description,
                enabled,
            )
        )

    def list_action_targets(self) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for row in self.store.list_audit():
            if row.action_type != "write_back":
                continue
            name = (row.parameters or {}).get("action_type")
            if isinstance(name, str) and name:
                latest[name] = {"created_at": row.created_at, "result": row.result}
        return {
            "targets": [
                action_target_payload(item, latest.get(item.action_type))
                for item in self.store.list_action_targets()
            ]
        }

    def delete_action_target(self, action_type: str) -> dict[str, Any]:
        self.store.delete_action_target(action_type)
        return {"deleted": action_type}

    # --- LLM-driven action proposal (the AIP equivalent) ---------------

    def propose_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        confidence: float,
        actor: str = "quinovo-ai",
        reason: str = "",
    ) -> dict[str, Any]:
        """Reason over the ontology and propose applying an action. HITL below 0.8."""
        payload: dict[str, Any] = {"action_type": action_type, "parameters": parameters}
        if reason:
            payload["reason"] = reason
        proposal, edited = submit_proposal(
            self, "action_application", payload, confidence, actor
        )
        result = {
            "proposal": proposal_payload(proposal),
            "hitl": proposal.status == "pending",
            "objects": [object_payload(self.store, item) for item in edited],
        }
        self.nudge()
        return result

    def tool_contract(self) -> dict[str, Any]:
        # Lazy: mcp/__init__ imports mcp.server, which imports this module.
        from quinovo.mcp.contract import adk_function_tools, hermes_skill, tool_specs

        return {
            "mcp": tool_specs(),
            "hermes": hermes_skill(),
            "adk": adk_function_tools(),
        }


def open_kernel(
    pack_dir: Path | None = None,
    db_path: Path | None = None,
) -> Kernel:
    return Kernel(pack_dir or DEFAULT_PACK, db_path or DEFAULT_DB)


__all__ = [
    "ActionError",
    "ConnectorError",
    "FunctionError",
    "Kernel",
    "LogicError",
    "PackCreateError",
    "ProposalError",
    "TrainError",
    "create_pack",
    "open_kernel",
]
