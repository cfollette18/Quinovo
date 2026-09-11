from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field

from quinovo.actions.apply import ActionError
from quinovo.ai.runtime import ProposalError
from quinovo.apps.audit_view import audit_html
from quinovo.apps.chat_view import chat_html
from quinovo.apps.connect_view import config_text, connect_html, signin_html
from quinovo.apps.connections import config_from_data_form
from quinovo.apps.inference_view import inference_html
from quinovo.apps.landing import landing_html
from quinovo.apps.logo_mocks import LOGO_MOCKS, logo_mocks_html
from quinovo.apps.object_view import object_view_html
from quinovo.apps.schema_manager import schema_manager_html
from quinovo.apps.session import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    has_passphrase,
    is_signed_in,
    issue_session_token,
    set_passphrase,
    verify_passphrase,
    verify_session_token,
)
from quinovo.apps.settings_view import settings_html
from quinovo.apps.train_view import train_html
from quinovo.chat.agent import handle_user_message
from quinovo.chat.sessions import delete_session, get_session, list_sessions
from quinovo.kernel import TrainError, open_kernel
from quinovo.llm.disagreement import ensure_disagreement_dataset
from quinovo.llm.tracing import flush_langfuse, load_langfuse_env
from quinovo.loop.runner import start_autonomy
from quinovo.workspace import DEFAULT_DB, DEFAULT_PACK, ROOT

__all__ = ["DEFAULT_DB", "DEFAULT_PACK", "ROOT", "create_app"]

CHROME_CSS = Path(__file__).resolve().parents[1] / "apps" / "chrome.css"
LANDING_CSS = Path(__file__).resolve().parents[1] / "apps" / "landing.css"
ASSETS_DIR = Path(__file__).resolve().parents[1] / "apps" / "assets"
LOGO_MOCKS_DIR = ASSETS_DIR / "logo-mocks"
AGENTS_ASSETS_DIR = ASSETS_DIR / "agents"
ACTIONS_ASSETS_DIR = ASSETS_DIR / "actions"
_LOGO_MOCK_FILES = {mock.filename for mock in LOGO_MOCKS}
_AGENT_ASSET_FILES = {p.name for p in AGENTS_ASSETS_DIR.glob("*.svg")} if AGENTS_ASSETS_DIR.is_dir() else set()
_ACTION_ASSET_FILES = {p.name for p in ACTIONS_ASSETS_DIR.glob("*.svg")} if ACTIONS_ASSETS_DIR.is_dir() else set()

# media types for the static brand assets served under /assets/
_ASSET_MEDIA = {
    "logo.svg": "image/svg+xml",
    "logo-mark.svg": "image/svg+xml",
    "logo-dark.svg": "image/svg+xml",
    "logo-full.svg": "image/svg+xml",
    "favicon.svg": "image/svg+xml",
    "favicon-32.png": "image/png",
    "logo.png": "image/png",
    "apple-touch-icon.png": "image/png",
}


def moved_permanently(to: str, request: Request) -> RedirectResponse:
    qs = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"{to}{qs}", status_code=301)


class ActionRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    actor: str = "local"
    fact_id: int | None = None


class TypeProposalRequest(BaseModel):
    type_def: dict[str, Any]
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


class TickRequest(BaseModel):
    actor: str = "autonomous"


class ChatPost(BaseModel):
    text: str
    session_id: str = ""


class ReviewRequest(BaseModel):
    actor: str = "human"


class ProposeRequest(BaseModel):
    kind: str
    payload: dict[str, Any]
    confidence: float
    actor: str = "quinovo-ai"


class TrainDatasetRequest(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)


class TrainJobRequest(BaseModel):
    name: str
    dataset_id: str
    size_class: str = "small"


class SourceRequest(BaseModel):
    name: str
    kind: str
    object_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False
    description: str = ""
    enabled: bool = True


class LogicSourceRequest(BaseModel):
    name: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False
    description: str = ""


class ActionTargetRequest(BaseModel):
    action_type: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    enabled: bool = True


def _form_redirect(request: Request) -> bool:
    content = (request.headers.get("content-type") or "").lower()
    return "application/x-www-form-urlencoded" in content or "multipart/form-data" in content


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.headers.get("x-quinovo-token")
    return header.strip() if header else None


class ProposeActionRequest(BaseModel):
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    actor: str = "quinovo-ai"
    reason: str = ""


def create_app(
    pack_dir: Path | None = None,
    db_path: Path | None = None,
) -> FastAPI:
    load_langfuse_env()
    ensure_disagreement_dataset()
    kernel = open_kernel(pack_dir, db_path)
    start_autonomy(kernel)
    kernel.nudge()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        start_autonomy(kernel)
        yield
        loop = getattr(kernel, "_autonomy", None)
        if loop is not None:
            loop.stop()
        flush_langfuse()

    app = FastAPI(
        title="Quinovo",
        version="0.1.0",
        description="Operational ontology. HTTP is the workspace; MCP is the agent surface.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.kernel = kernel

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        from quinovo.llm.engine import status_payload

        return {
            "status": "ok",
            "ontology": kernel.ontology.ontology.api_name,
            "auto_apply_min_confidence": kernel.ontology.ontology.auto_apply_min_confidence,
            "llm": status_payload(),
        }

    @app.get("/assets/chrome.css")
    def chrome_css() -> FileResponse:
        return FileResponse(CHROME_CSS, media_type="text/css")

    @app.get("/assets/landing.css")
    def landing_css() -> FileResponse:
        return FileResponse(LANDING_CSS, media_type="text/css")

    def _asset_response(name: str) -> FileResponse:
        return FileResponse(ASSETS_DIR / name, media_type=_ASSET_MEDIA[name])

    @app.get("/assets/logo.svg")
    def asset_logo_svg() -> FileResponse:
        return _asset_response("logo.svg")

    @app.get("/assets/logo-mark.svg")
    def asset_logo_mark_svg() -> FileResponse:
        return _asset_response("logo-mark.svg")

    @app.get("/assets/logo-dark.svg")
    def asset_logo_dark_svg() -> FileResponse:
        return _asset_response("logo-dark.svg")

    @app.get("/assets/logo-full.svg")
    def asset_logo_full_svg() -> FileResponse:
        return _asset_response("logo-full.svg")

    @app.get("/assets/favicon.svg")
    def asset_favicon_svg() -> FileResponse:
        return _asset_response("favicon.svg")

    @app.get("/assets/favicon-32.png")
    def asset_favicon_png() -> FileResponse:
        return _asset_response("favicon-32.png")

    @app.get("/assets/logo.png")
    def asset_logo_png() -> FileResponse:
        return _asset_response("logo.png")

    @app.get("/assets/apple-touch-icon.png")
    def asset_apple_touch_icon() -> FileResponse:
        return _asset_response("apple-touch-icon.png")

    @app.get("/assets/logo-mocks/{filename}")
    def logo_mock_asset(filename: str) -> FileResponse:
        if filename not in _LOGO_MOCK_FILES:
            raise HTTPException(status_code=404, detail="Unknown logo mock")
        path = LOGO_MOCKS_DIR / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Logo mock missing")
        # Sources keep a .png name; the bytes are JPEG (JFIF). Serve the real type
        # so the browser will paint the image instead of treating it as a broken PNG.
        return FileResponse(path, media_type="image/jpeg")

    def _svg_asset(directory: Path, allow: set[str], filename: str) -> FileResponse:
        if filename not in allow:
            raise HTTPException(status_code=404, detail="Unknown asset")
        path = directory / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Asset missing")
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/assets/agents/{filename}")
    def agent_asset(filename: str) -> FileResponse:
        return _svg_asset(AGENTS_ASSETS_DIR, _AGENT_ASSET_FILES, filename)

    @app.get("/assets/actions/{filename}")
    def action_asset(filename: str) -> FileResponse:
        return _svg_asset(ACTIONS_ASSETS_DIR, _ACTION_ASSET_FILES, filename)

    @app.get("/logo-mocks", response_class=HTMLResponse)
    def logo_mocks_page() -> str:
        return logo_mocks_html()

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request) -> str:
        return landing_html(signed_in=is_signed_in(request))

    # --- Local sign-in + guided connect flow ---

    @app.get("/signin", response_class=HTMLResponse)
    def signin_page(request: Request, next: str = "/connect") -> str:
        # Already signed in? Skip straight to the connect flow.
        if verify_session_token(request.cookies.get(COOKIE_NAME)):
            return RedirectResponse(next or "/connect", status_code=303)
        return signin_html(next_path=next, first_visit=not has_passphrase())

    @app.post("/signin")
    def signin_submit(
        request: Request,
        passphrase: str = Form(...),
        next: str = Form("/connect"),
    ):
        target = next or "/connect"
        if not has_passphrase():
            # First visit: claim the instance by setting the passphrase.
            try:
                set_passphrase(passphrase)
            except (FileExistsError, ValueError) as exc:
                return HTMLResponse(
                    signin_html(
                        next_path=target,
                        error=str(exc) or "Could not set passphrase.",
                        first_visit=False,
                    ),
                    status_code=400,
                )
        elif not verify_passphrase(passphrase):
            return HTMLResponse(
                signin_html(
                    next_path=target,
                    error="That passphrase doesn't match this Quinovo instance.",
                    first_visit=False,
                ),
                status_code=401,
            )
        token = issue_session_token()
        resp = RedirectResponse(target, status_code=303)
        resp.set_cookie(
            COOKIE_NAME, token, max_age=COOKIE_MAX_AGE,
            httponly=True, samesite="lax", path="/",
        )
        return resp

    @app.post("/signout")
    def signout_submit(request: Request):
        resp = RedirectResponse("/", status_code=303)
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    @app.get("/connect", response_class=HTMLResponse)
    def connect_page(request: Request) -> str:
        if not verify_session_token(request.cookies.get(COOKIE_NAME)):
            return RedirectResponse("/signin?next=/connect", status_code=303)
        return connect_html(kernel.pack_dir, kernel.store.db_path, signed_in=True)

    @app.post("/connect/test")
    def connect_test(request: Request) -> dict[str, Any]:
        if not verify_session_token(request.cookies.get(COOKIE_NAME)):
            raise HTTPException(401, "sign in required")
        # Deliberately do NOT echo LLM key metadata here — keep the connect
        # flow free of any key material (even tail/set flags).
        return {
            "ok": True,
            "status": "reachable",
            "ontology": kernel.ontology.ontology.api_name,
            "auto_apply_min_confidence": kernel.ontology.ontology.auto_apply_min_confidence,
        }

    @app.get("/connect/config/{agent_id}")
    def connect_config(request: Request, agent_id: str) -> str:
        # Returns the full JSON/YAML config as plain text for the copy button.
        # It is never rendered as a JSON block on any page; the browser puts
        # it straight on the clipboard. Requires a session like the rest of
        # /connect.
        if not verify_session_token(request.cookies.get(COOKIE_NAME)):
            raise HTTPException(401, "sign in required")
        pack = str(kernel.pack_dir.resolve())
        db = str(kernel.store.db_path.resolve())
        return PlainTextResponse(config_text(agent_id, pack, db))

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page() -> str:
        return chat_html(pack_name=kernel.ontology.ontology.display_name)

    @app.get("/chat/sessions")
    def chat_sessions() -> dict[str, Any]:
        return {"sessions": list_sessions()}

    @app.get("/chat/sessions/{session_id}")
    def chat_session(session_id: str) -> dict[str, Any]:
        try:
            return get_session(session_id).public()
        except KeyError as exc:
            raise HTTPException(404, "chat not found") from exc

    @app.delete("/chat/sessions/{session_id}")
    def chat_delete(session_id: str) -> dict[str, Any]:
        delete_session(session_id)
        return {"ok": True}

    @app.post("/chat/stream")
    def chat_stream(body: ChatPost) -> StreamingResponse:
        def events():
            for event in handle_user_message(kernel, body.text, session_id=body.session_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/twin")
    def twin_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/chat", request)

    @app.get("/graph")
    def graph_page_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/chat", request)

    @app.get("/workspace")
    def workspace_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/chat", request)

    @app.get("/graph.json")
    def graph() -> dict[str, Any]:
        return kernel.graph()

    @app.get("/ontology")
    def ontology_meta() -> dict[str, Any]:
        return kernel.ontology.model_dump()

    @app.get("/objects/{object_type}")
    def list_objects(
        object_type: str,
        actor: str | None = None,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> dict[str, Any]:
        try:
            kernel.ontology.object_type(object_type)
        except KeyError as exc:
            raise HTTPException(404, f"unknown object type {object_type}") from exc
        return kernel.filter_objects(object_type, property_name, equals, actor)

    @app.get("/objects/{object_type}/{id}")
    def get_object(object_type: str, id: str, actor: str | None = None) -> dict[str, Any]:
        try:
            return kernel.get_object(object_type, id, actor=actor)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/objects/{object_type}/{id}/links/{side}")
    def search_around(object_type: str, id: str, side: str) -> dict[str, Any]:
        try:
            return kernel.search_around(object_type, id, side)
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

    @app.get("/audit.json")
    def audit_json(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        from quinovo.engine.payloads import audit_payload

        rows = kernel.store.list_audit()[-limit:]
        return {"entries": [audit_payload(row) for row in rows]}

    @app.post("/tick")
    def tick(body: TickRequest | None = None) -> dict[str, Any]:
        actor = body.actor if body is not None else "autonomous"
        return kernel.tick(actor)

    @app.post("/ai/types")
    def ai_types(body: TypeProposalRequest) -> dict[str, Any]:
        try:
            return kernel.propose("type_definition", body.type_def, body.confidence, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/ai/classify")
    def ai_classify(body: ClassifyRequest) -> dict[str, Any]:
        payload = {"object_type": body.object_type, "properties": body.properties}
        try:
            return kernel.propose("classification", payload, body.confidence, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/ai/propose")
    def ai_propose(body: ProposeRequest) -> dict[str, Any]:
        try:
            return kernel.propose(body.kind, body.payload, body.confidence, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/proposals")
    def proposals(status: str | None = None) -> dict[str, Any]:
        return kernel.list_proposals(status)

    @app.post("/proposals/{proposal_id}/approve")
    def proposal_approve(proposal_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            return kernel.approve_proposal(proposal_id, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/proposals/{proposal_id}/reject")
    def proposal_reject(proposal_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            return kernel.reject_proposal(proposal_id, body.actor)
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

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

    @app.get("/view/{object_type}/{id}", response_class=HTMLResponse)
    def object_view(object_type: str, id: str) -> str:
        try:
            data = kernel.object_view_data(object_type, id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return object_view_html(
            data["object"],
            data["actions"],
            data["links"],
            data["series"],
            pack_name=data["pack_name"],
        )

    @app.get("/catalog", response_class=HTMLResponse)
    def catalog(created: str = Query("")) -> str:
        names = [part for part in created.split(",") if part.strip()]
        data = kernel.catalog_data()
        return schema_manager_html(
            kernel.ontology,
            data["counts"],
            topics=data["topics"],
            created=names,
        )

    @app.get("/manager")
    def manager_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/catalog", request)

    def _organize(actor: str) -> RedirectResponse:
        result = kernel.organize_topics(actor, use_llm=True)
        created = ",".join(result.get("created") or [])
        target = "/catalog?created=" + created if created else "/catalog"
        return RedirectResponse(target, status_code=303)

    @app.post("/catalog/organize")
    def catalog_organize(actor: str = Form("human")) -> RedirectResponse:
        return _organize(actor)

    @app.post("/manager/organize")
    def manager_organize(actor: str = Form("human")) -> RedirectResponse:
        return _organize(actor)

    @app.get("/inference", response_class=HTMLResponse)
    def inference_page() -> str:
        queue = kernel.inference_queue()
        return inference_html(
            kernel.ontology,
            queue["facts"],
            queue["proposals"],
            queue["pending_actions"],
        )

    @app.get("/logic")
    def logic_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/inference", request)

    @app.get("/inference.json")
    @app.get("/logic.json")
    def inference_json() -> dict[str, Any]:
        return kernel.inference_queue()

    @app.get("/audit", response_class=HTMLResponse)
    def audit_page() -> str:
        return audit_html(kernel.ontology, kernel.store.list_audit()[-80:])

    @app.get("/history")
    def history_moved(request: Request) -> RedirectResponse:
        return moved_permanently("/audit", request)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page() -> str:
        from quinovo.llm.settings import ensure_settings

        return settings_html(
            ensure_settings(),
            pack_name=kernel.ontology.ontology.display_name,
        )

    @app.get("/settings.json")
    def settings_json() -> dict[str, Any]:
        from quinovo.llm.engine import status_payload
        from quinovo.llm.settings import ensure_settings

        return status_payload(ensure_settings())

    @app.post("/settings")
    def settings_save(
        intent: str = Form("save"),
        provider: str = Form(""),
        model: str = Form(""),
        base_url: str = Form(""),
        api_key: str = Form(""),
        protocol: str = Form(""),
        enabled: str = Form(""),
    ) -> RedirectResponse:
        from quinovo.llm.hermes import import_hermes
        from quinovo.llm.settings import save_settings, update_settings

        if intent == "import_hermes":
            save_settings(import_hermes())
        else:
            update_settings(
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                protocol=protocol,
                enabled=enabled == "on",
                source="manual",
            )
        return RedirectResponse("/settings", status_code=303)

    @app.post("/settings/test")
    def settings_test() -> dict[str, Any]:
        from quinovo.llm.engine import LLMError, engine_from_settings

        try:
            text = engine_from_settings().complete(
                "Reply with the single word ok.",
                max_tokens=16,
                feature="test-connection",
            )
        except LLMError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "message": "Connected.", "preview": text[:80]}

    @app.get("/objects/{object_type}/{id}/series/{metric}")
    def series(object_type: str, id: str, metric: str) -> dict[str, Any]:
        try:
            return kernel.get_series(object_type, id, metric)
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
        return kernel.list_pending_actions()

    @app.post("/pending-actions/{pending_id}/approve")
    def pending_action_approve(pending_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            return kernel.approve_pending_action(pending_id, body.actor)
        except (KeyError, ActionError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/pending-actions/{pending_id}/reject")
    def pending_action_reject(pending_id: int, body: ReviewRequest) -> dict[str, Any]:
        try:
            return kernel.reject_pending_action(pending_id, body.actor)
        except (KeyError, ActionError) as exc:
            raise HTTPException(400, str(exc)) from exc

    def _train_filters(
        kinds: str | None = None,
        types: str | None = None,
        status: str | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
        include_fields: str | None = None,
        exclude_fields: str | None = None,
        only_approved: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        approved = str(only_approved or "").lower() in {"1", "true", "on", "yes"}
        try:
            return kernel.train_filters(
                kinds=kinds,
                types=types,
                status=status,
                q=q,
                since=since,
                until=until,
                include_fields=include_fields,
                exclude_fields=exclude_fields,
                only_approved=approved,
                limit=limit,
            )
        except TrainError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/train", response_class=HTMLResponse)
    def train_page(
        kinds: str | None = None,
        types: str | None = None,
        status: str | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
        include_fields: str | None = None,
        exclude_fields: str | None = None,
        only_approved: str | None = None,
    ) -> str:
        filters = _train_filters(
            kinds,
            types,
            status,
            q,
            since,
            until,
            include_fields,
            exclude_fields,
            only_approved,
        )
        return train_html(
            kernel.ontology,
            kernel.train_preview(filters),
            kernel.list_train_datasets()["datasets"],
            kernel.list_train_jobs()["jobs"],
        )

    @app.get("/train/data")
    def train_data(
        kinds: str | None = None,
        types: str | None = None,
        status: str | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
        include_fields: str | None = None,
        exclude_fields: str | None = None,
        only_approved: str | None = None,
        limit: int | None = Query(default=None, ge=1, le=5000),
    ) -> dict[str, Any]:
        return kernel.train_preview(
            _train_filters(
                kinds,
                types,
                status,
                q,
                since,
                until,
                include_fields,
                exclude_fields,
                only_approved,
                limit,
            )
        )

    @app.get("/train/datasets")
    def train_datasets() -> dict[str, Any]:
        return kernel.list_train_datasets()

    @app.post("/train/datasets")
    def train_datasets_create(body: TrainDatasetRequest) -> dict[str, Any]:
        try:
            filters = kernel.train_filters(**body.filters)
            return kernel.save_train_dataset(body.name, filters)
        except TrainError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/train/jobs")
    def train_jobs() -> dict[str, Any]:
        return kernel.list_train_jobs()

    @app.post("/train/jobs")
    def train_jobs_create(body: TrainJobRequest) -> dict[str, Any]:
        try:
            return kernel.create_train_job(body.name, body.dataset_id, body.size_class)
        except TrainError as exc:
            raise HTTPException(400, str(exc)) from exc

    # --- Connections: data sources, external logic, action write-backs ---

    @app.get("/sources", response_class=HTMLResponse)
    def sources_page(add: str = "", layer: str = "data") -> str:
        from quinovo.apps.sources_view import sources_html

        object_types = [item["api_name"] for item in kernel.list_object_types()["object_types"]]
        action_types = [item["api_name"] for item in kernel.list_actions()["actions"]]
        return sources_html(
            kernel.list_sources()["sources"],
            kernel.list_logic_sources()["logic_sources"],
            kernel.list_action_targets()["targets"],
            kernel.list_source_runs(20)["runs"],
            pack_name=kernel.ontology.ontology.display_name,
            add=add,
            layer=layer,
            object_types=object_types,
            action_types=action_types,
        )

    @app.get("/sources.json")
    def sources_json() -> dict[str, Any]:
        return {
            "sources": kernel.list_sources()["sources"],
            "logic_sources": kernel.list_logic_sources()["logic_sources"],
            "action_targets": kernel.list_action_targets()["targets"],
            "runs": kernel.list_source_runs(20)["runs"],
        }

    @app.post("/sources")
    def sources_create(body: SourceRequest) -> dict[str, Any]:
        try:
            return kernel.register_source(
                body.name, body.kind, body.object_type, body.config,
                auto=body.auto, description=body.description,
                enabled=body.enabled,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/sources/form")
    def sources_form(
        name: str = Form(...),
        kind: str = Form(...),
        object_type: str = Form(...),
        url: str = Form(""),
        path: str = Form(""),
        dsn: str = Form(""),
        query: str = Form(""),
        tool: str = Form(""),
        command: str = Form(""),
        token: str = Form(""),
        rows_path: str = Form(""),
        id_field: str = Form(""),
        property_map: str = Form(""),
        auto: str = Form(""),
        description: str = Form(""),
        topic: str = Form(""),
    ) -> RedirectResponse:
        fields = {
            "url": url,
            "path": path,
            "dsn": dsn,
            "query": query,
            "tool": tool,
            "command": command,
            "token": token,
            "rows_path": rows_path,
            "id_field": id_field,
            "property_map": property_map,
            "topic": topic,
        }
        try:
            config = config_from_data_form(kind, fields)
            kernel.register_source(
                name,
                kind,
                object_type,
                config,
                auto=auto == "on",
                description=description,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/{name}/pull")
    def sources_pull(name: str, request: Request) -> Any:
        try:
            result = kernel.pull_source(name)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if _form_redirect(request):
            return RedirectResponse("/sources", status_code=303)
        return result

    @app.post("/sources/{name}/enabled")
    def sources_enabled(name: str, enabled: str = Form("on")) -> RedirectResponse:
        try:
            kernel.set_source_enabled(name, enabled == "on")
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/{name}/delete")
    def sources_delete_form(name: str) -> RedirectResponse:
        kernel.delete_source(name)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/sources/pull-all")
    def sources_pull_all() -> dict[str, Any]:
        return kernel.pull_all_sources()

    @app.delete("/sources/{name}")
    def sources_delete(name: str) -> dict[str, Any]:
        return kernel.delete_source(name)

    @app.post("/ingest/{name}")
    async def ingest_source(name: str, request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(400, "body must be JSON") from exc
        try:
            return kernel.ingest_source(name, payload, token=_bearer_token(request))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/logic-sources")
    def logic_sources_create(body: LogicSourceRequest) -> dict[str, Any]:
        try:
            return kernel.register_logic_source(
                body.name, body.kind, body.config,
                auto=body.auto, description=body.description,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/logic-sources/{name}/run")
    def logic_sources_run(name: str, request: Request) -> Any:
        try:
            result = kernel.run_logic_source(name)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if _form_redirect(request):
            return RedirectResponse("/sources", status_code=303)
        return result

    @app.delete("/logic-sources/{name}")
    def logic_sources_delete(name: str) -> dict[str, Any]:
        return kernel.delete_logic_source(name)

    @app.post("/action-targets")
    def action_targets_create(body: ActionTargetRequest) -> dict[str, Any]:
        try:
            return kernel.register_action_target(
                body.action_type,
                body.kind,
                body.config,
                description=body.description,
                enabled=body.enabled,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/action-targets/form")
    def action_targets_form(
        action_type: str = Form(...),
        kind: str = Form(...),
        url: str = Form(""),
        token: str = Form(""),
        to: str = Form(""),
        smtp_host: str = Form(""),
        smtp_user: str = Form(""),
        smtp_password: str = Form(""),
        tool: str = Form(""),
        dsn: str = Form(""),
        statement: str = Form(""),
        allowed_tables: str = Form(""),
        description: str = Form(""),
    ) -> RedirectResponse:
        from quinovo.apps.connections import config_from_action_form

        fields = {
            "url": url,
            "token": token,
            "to": to,
            "smtp_host": smtp_host,
            "smtp_user": smtp_user,
            "smtp_password": smtp_password,
            "tool": tool,
            "dsn": dsn,
            "statement": statement,
            "allowed_tables": allowed_tables,
        }
        try:
            config = config_from_action_form(kind, fields)
            kernel.register_action_target(action_type, kind, config, description=description)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/sources", status_code=303)

    @app.get("/action-targets")
    def action_targets_list() -> dict[str, Any]:
        return kernel.list_action_targets()

    @app.post("/action-targets/{action_type}/enabled")
    def action_targets_enabled(action_type: str, enabled: str = Form("on")) -> RedirectResponse:
        try:
            kernel.set_action_target_enabled(action_type, enabled == "on")
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return RedirectResponse("/sources", status_code=303)

    @app.post("/action-targets/{action_type}/delete")
    def action_targets_delete_form(action_type: str) -> RedirectResponse:
        kernel.delete_action_target(action_type)
        return RedirectResponse("/sources", status_code=303)

    @app.delete("/action-targets/{action_type}")
    def action_targets_delete(action_type: str) -> dict[str, Any]:
        return kernel.delete_action_target(action_type)

    @app.post("/ai/propose-action")
    def ai_propose_action(body: ProposeActionRequest) -> dict[str, Any]:
        try:
            return kernel.propose_action(
                body.action_type, body.parameters, body.confidence, body.actor, body.reason
            )
        except ProposalError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/contract")
    def contract() -> dict[str, Any]:
        return kernel.tool_contract()

    @app.get("/sdk", response_class=HTMLResponse)
    def sdk_page() -> str:
        from quinovo.apps.sdk_view import sdk_html

        return sdk_html(kernel.tool_contract(), pack_name=kernel.ontology.ontology.display_name)

    return app
