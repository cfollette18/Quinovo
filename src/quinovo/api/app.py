from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from quinovo.actions.apply import ActionError
from quinovo.ai.runtime import (
    ProposalError,
    approve_proposal,
    reject_proposal,
    submit_proposal,
)
from quinovo.kernel import open_kernel
from quinovo.paths import DEFAULT_DB, EXAMPLE_PACK, ROOT
from quinovo.payloads import object_payload, proposal_payload

__all__ = ["DEFAULT_DB", "EXAMPLE_PACK", "ROOT", "create_app"]


class ActionRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor: str = "local"
    fact_id: int | None = None


class TypeProposalRequest(BaseModel):
    type: dict[str, Any]
    confidence: float
    actor: str = "quinovo-ai"


class ClassifyRequest(BaseModel):
    object_type: str
    properties: dict[str, Any]
    confidence: float
    actor: str = "quinovo-ai"


class ForecastRequest(BaseModel):
    object_type: str
    id: str
    metric: str
    horizon_hours: float
    point: float
    model: str
    confidence: float
    q10: float | None = None
    q90: float | None = None


class ReviewRequest(BaseModel):
    actor: str = "human"


def create_app(
    pack_dir: Path | None = None,
    db_path: Path | None = None,
) -> FastAPI:
    kernel = open_kernel(pack_dir, db_path)
    store = kernel.store
    ontology = kernel.ontology

    app = FastAPI(
        title="Quinovo",
        version="0.1.0",
        description="Operational ontology MCP kernel. HTTP is a debug surface.",
    )
    app.state.kernel = kernel
    app.state.store = store
    app.state.ruleset = kernel.ruleset

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "ontology": ontology.ontology.api_name,
            "auto_apply_min_confidence": ontology.ontology.auto_apply_min_confidence,
        }

    @app.get("/ontology")
    def ontology_meta() -> dict[str, Any]:
        return ontology.model_dump(by_alias=True)

    @app.get("/objects/{object_type}")
    def list_objects(
        object_type: str,
        actor: str | None = None,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> dict[str, Any]:
        try:
            ontology.object_type(object_type)
        except KeyError as exc:
            raise HTTPException(404, f"unknown object type {object_type}") from exc
        return kernel.filter_objects(object_type, property_name, equals, actor)

    @app.get("/objects/{object_type}/{pk}")
    def get_object(object_type: str, pk: str, actor: str | None = None) -> dict[str, Any]:
        try:
            return kernel.get_object(object_type, pk, actor=actor)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/objects/{object_type}/{pk}/links/{side}")
    def search_around(object_type: str, pk: str, side: str) -> dict[str, Any]:
        try:
            return kernel.search_around(object_type, pk, side)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/actions/{action_type}")
    def post_action(action_type: str, body: ActionRequest) -> dict[str, Any]:
        try:
            return kernel.apply_action(
                action_type,
                body.parameters,
                body.actor,
                channel="human",
                fact_id=body.fact_id,
            )
        except ActionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/audit")
    def audit(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        rows = store.list_audit()[-limit:]
        return {
            "entries": [
                {
                    "id": row.id,
                    "action_type": row.action_type,
                    "actor": row.actor,
                    "at": row.at,
                    "parameters": row.parameters,
                    "result": row.result,
                }
                for row in rows
            ]
        }

    @app.post("/ai/types")
    def ai_types(body: TypeProposalRequest) -> dict[str, Any]:
        try:
            proposal, edited = submit_proposal(
                store, "type_definition", body.type, body.confidence, body.actor
            )
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "proposal": proposal_payload(proposal),
            "hitl": proposal.status == "pending",
            "objects": [object_payload(store, o) for o in edited],
        }

    @app.post("/ai/classify")
    def ai_classify(body: ClassifyRequest) -> dict[str, Any]:
        payload = {"object_type": body.object_type, "properties": body.properties}
        try:
            proposal, edited = submit_proposal(
                store, "classification", payload, body.confidence, body.actor
            )
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "proposal": proposal_payload(proposal),
            "hitl": proposal.status == "pending",
            "objects": [object_payload(store, o) for o in edited],
        }

    @app.get("/proposals")
    def proposals(status: str | None = None) -> dict[str, Any]:
        return {"proposals": [proposal_payload(p) for p in store.list_proposals(status)]}

    @app.post("/proposals/{proposal_id}/approve")
    def proposal_approve(proposal_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            proposal, edited = approve_proposal(store, proposal_id, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "proposal": proposal_payload(proposal),
            "objects": [object_payload(store, o) for o in edited],
        }

    @app.post("/proposals/{proposal_id}/reject")
    def proposal_reject(proposal_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            proposal = reject_proposal(store, proposal_id, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"proposal": proposal_payload(proposal)}

    @app.post("/ai/forecasts")
    def ai_forecasts(body: ForecastRequest) -> dict[str, Any]:
        try:
            return kernel.write_forecast(
                body.object_type,
                body.id,
                body.metric,
                body.horizon_hours,
                body.point,
                body.model,
                body.confidence,
                q10=body.q10,
                q90=body.q90,
            )
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/inference/run")
    def inference_run() -> dict[str, Any]:
        try:
            return kernel.run_inference()
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/inference/facts")
    def inference_facts(status: str | None = None) -> dict[str, Any]:
        return kernel.list_inferred_facts(status=status)

    @app.post("/inference/facts/{fact_id}/approve")
    def inference_approve(fact_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            return kernel.approve_inferred_fact(fact_id, body.actor)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/view/{object_type}/{pk}", response_class=HTMLResponse)
    def object_view(object_type: str, pk: str) -> str:
        try:
            return kernel.object_view(object_type, pk)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/manager", response_class=HTMLResponse)
    def manager() -> str:
        return kernel.schema_manager()

    @app.get("/objects/{object_type}/{pk}/series/{metric}")
    def series(object_type: str, pk: str, metric: str) -> dict[str, Any]:
        try:
            return kernel.get_series(object_type, pk, metric)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/functions/{api_name}")
    def functions(api_name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return {"result": kernel.run_pack_function(api_name, body or {})}
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/pending-actions")
    def pending_actions() -> dict[str, Any]:
        return {"actions": kernel.store.list_pending_actions()}

    return app
