"""Domain-blind ontology kernel. MCP and HTTP both call this."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quinovo.actions.apply import ActionError, apply_action
from quinovo.adapters import adk_function_tools, hermes_skill, tool_specs
from quinovo.ai.runtime import ProposalError, write_forecast
from quinovo.apps.object_view import object_view_html
from quinovo.apps.schema_manager import schema_manager_html
from quinovo.engine.store import ObjectStore
from quinovo.functions import FunctionError, FunctionManifest, load_functions, run_function
from quinovo.funnel.seed import load_seed
from quinovo.inference.engine import approve_inferred_fact, run_inference
from quinovo.inference.load import load_ruleset
from quinovo.inference.rules import InferenceRuleset
from quinovo.language.load import load_ontology
from quinovo.language.models import Ontology
from quinovo.models import forecast_metric
from quinovo.paths import DEFAULT_DB, EXAMPLE_PACK
from quinovo.payloads import forecast_payload, inferred_payload, object_payload
from quinovo.policy import ActionChannel
from quinovo.propose import propose_from_files
from quinovo.security import Guard, load_security, seed_tuples


class Kernel:
    def __init__(self, pack_dir: Path, db_path: Path) -> None:
        self.pack_dir = pack_dir
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
        if seed.exists() and not self.store.list_objects(self.ontology.object_types[0].api_name):
            load_seed(self.store, seed)

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
        payload["series"] = {}
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
        return {
            "audit_id": audit.id,
            "action_type": audit.action_type,
            "actor": audit.actor,
            "at": audit.at,
            "result": audit.result,
            "parameters": audit.parameters,
            "objects": [object_payload(self.store, item) for item in edited],
        }

    def approve_pending_action(self, pending_id: int, actor: str) -> dict[str, Any]:
        pending = next(
            (row for row in self.store.list_pending_actions() if row["id"] == pending_id),
            None,
        )
        if pending is None:
            raise KeyError(pending_id)
        self.store.set_pending_action_status(pending_id, "approved")
        return self.apply_action(
            pending["action_type"],
            pending["parameters"],
            actor,
            channel="human",
            already_approved=True,
        )

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
        return {"forecast": forecast_payload(self.store, forecast)}

    def append_series(
        self, object_type: str, id: str, metric: str, ts: str, value: float
    ) -> None:
        self.store.append_series_point(object_type, id, metric, ts, value)

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
        return propose_from_files(self.store, root, confidence, actor)

    def object_view(self, object_type: str, id: str) -> str:
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
        return object_view_html(payload, self.list_actions()["actions"], links, series)

    def schema_manager(self) -> str:
        return schema_manager_html(self.ontology)

    def approve_inferred_fact(self, fact_id: int, actor: str) -> dict[str, Any]:
        fact = approve_inferred_fact(self.store, fact_id, actor, self.ruleset)
        return {"fact": inferred_payload(fact)}

    def reload_seed(self) -> None:
        seed = self.pack_dir / "seed.yaml"
        if not seed.exists():
            raise FileNotFoundError(seed)
        load_seed(self.store, seed)

    def tool_contract(self) -> dict[str, Any]:
        return {
            "mcp": tool_specs(),
            "hermes": hermes_skill(),
            "adk": adk_function_tools(),
        }


def open_kernel(
    pack_dir: Path | None = None,
    db_path: Path | None = None,
) -> Kernel:
    return Kernel(pack_dir or EXAMPLE_PACK, db_path or DEFAULT_DB)


__all__ = ["ActionError", "FunctionError", "Kernel", "ProposalError", "open_kernel"]
