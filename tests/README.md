# Tests

Run everything with `make test` from the repo root. Fixtures live in
`tests/fixtures/`; `conftest.py` provides the `client` fixture (a TestClient
over a temp copy of the example pack) and isolates LLM settings and session
data per test.

The `test_milestone_*.py` files correspond to the build phases in
`research/plan.md` (Phase A–D); `test_acceptance.py` is the v0.1 acceptance
pass over the example pack.

| File | Covers |
|---|---|
| `test_acceptance.py` | End-to-end v0.1 acceptance: `language/load.py`, kernel reads, REST object routes |
| `test_milestone_b.py` | Phase B (anyone's pack): `pack/init.py`, pack loading, `mcp/contract.py` Hermes/ADK surfaces |
| `test_milestone_c.py` | Phase C (real inference): `inference/` rules engine, series, `inference/forecasting.py` backends |
| `test_milestone_d.py` | Phase D (governed production): `security.py` policy enforcement, `engine/sql.py`, object/catalog views via HTTP |
| `test_action_proposals.py` | `actions/apply.py` + `ai/runtime.py` action_application proposals and HITL |
| `test_action_targets.py` | `actions/dispatch.py` write-back targets (webhook, slack, email, mcp, sql) |
| `test_autonomy.py` | `loop/runner.py` and `loop/tick.py`: nudge/wake, reload keeps the runner, workspace serve paths |
| `test_brand_assets.py` | `apps/` static brand assets served under `/assets/` |
| `test_cli_create.py` | `cli.py create` command against `pack/create.py` |
| `test_connect_flow.py` | `apps/connect_view.py` + `apps/session.py` sign-in and connect flow |
| `test_connections_http.py` | `/sources`, `/logic-sources`, `/action-targets` REST routes |
| `test_connectors.py` | `connectors/` registry and source kinds, pull/upsert mapping |
| `test_dashboard.py` | `apps/` workspace pages over the clinic fixture pack |
| `test_funnel_overlay.py` | `funnel/seed.py` seed loading and property overlays |
| `test_hitl_and_forecasts.py` | Forecast write path, confidence threshold, HITL review queue |
| `test_inference.py` | `inference/engine.py` rule kinds and `explain_fact` provenance |
| `test_llm_settings.py` | `llm/settings.py`, `llm/hermes.py` import, `llm/engine.py` errors |
| `test_llm_tracing.py` | `llm/tracing.py` Langfuse observation hooks |
| `test_logic_sources.py` | `logic/` registry and external logic sources |
| `test_logo_mocks.py` | `apps/logo_mocks.py` and the logo-mocks page |
| `test_mcp.py` | `mcp/server.py` tools and `mcp/contract.py` `tool_specs()` parity |
| `test_pack_create.py` | `pack/create.py` spec validation and scaffold |
| `test_pack_validation.py` | `pack/validate.py` cross-file checks over every pack under `packs/` and the fixtures |
| `test_store_schema.py` | `engine/store.py` schema, migrations, typed records |
| `test_topics.py` | `topics.py` topic baskets and the catalog view data |
| `test_train.py` | `train/` filters, datasets, jobs and the `/train` routes |
| `test_universal_connectors.py` | `connectors/` http/json/csv/sql/mcp kinds incl. `engine/sql.py` DSN handling |
| `test_world_capture.py` | `capture.py` and the `connectors/transcripts.py` ingest path on the world pack |
