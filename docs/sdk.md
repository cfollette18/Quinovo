# The Quinovo SDK: the ontology, callable

Quinovo does not ship a proprietary SDK you install. Its SDK is **MCP plus the HTTP API** — one typed surface any external app can call to read objects, walk named links, run actions, and get inferred facts. If your client speaks MCP, it already speaks Quinovo.

## MCP surface (stdio)

Start Quinovo as an MCP server and point any MCP-compatible client at it:

```bash
uv run quinovo mcp --pack /abs/path/to/your/pack --db /abs/path/to/quinovo.sqlite
```

The tool list is generated from the loaded pack. The full set (see `contract` / `tool_specs()`):

- **Loop:** `tick` — pulls sources, enriches new turns with semantic connections, authors proposals, infers, applies unattended actions, returns HITL. A background loop already runs this; agents never need to be told "quinovo tick".
- **Capture:** `remember` — one call with raw turn text writes the Conversation plus human-style semantic connections (linked Facts, Memories, Persons). Prefer it over `save_turn` unless you already have structured items.
- **Reads:** `list_object_types`, `get_object`, `search_around`, `filter_objects`, `list_links`, `list_inferred_facts`, `explain_fact`, `get_series`, `graph`.
- **Writes (the only legal writes):** `apply_action`, `upsert_object`, `set_link`, `remove_link`, `delete_object`, `append_series`.
- **Authoring (humans never write YAML):** `propose`, `propose_pack`, `propose_rule`, `propose_type`, `propose_action` — all HITL below 0.8.
- **Connectors (data in):** `register_source`, `list_sources`, `pull_source`, `pull_sources`, `ingest_source`, `delete_source`.
- **Logic (lives anywhere):** `register_logic_source`, `list_logic_sources`, `run_logic_source`, `run_logic`, `delete_logic_source`.
- **Systems of action (write-back):** `register_action_target`, `list_action_targets`, `delete_action_target`.
- **Review (the only human job):** `approve_proposal`, `reject_proposal`, `approve_inferred_fact`, `approve_pending_action`, `list_proposals`, `list_pending_actions`.
- **Contract:** `contract` — the same surface for MCP, Hermes, and Google ADK.

## HTTP API

The workspace is also an HTTP API (Databricks-styled chrome, JSON behind a toggle):

| Surface | Route |
|---------|-------|
| Graph | `GET /graph` |
| Objects | `GET /objects/{type}`, `GET /objects/{type}/{pk}` |
| Links | `GET /objects/{type}/{pk}/links/{side}` |
| Actions | `POST /actions/{action_type}` |
| Sources | `GET/POST /sources`, `POST /sources/{name}/pull`, `POST /ingest/{name}` |
| Logic | `POST /logic-sources`, `POST /logic-sources/{name}/run` |
| Targets | `GET/POST /action-targets` |
| AI proposals | `POST /ai/propose-action` |
| Contract | `GET /contract` |

## Bidirectional MCP

Quinovo **exposes itself as MCP** (above) and can also **consume** MCP-style sources. The connector layer *is* MCP — there is no marketplace of hundreds of adapters. A web address, a file, a push, a SQL query, or another MCP server becomes a `register_source`; any endpoint that returns facts becomes a `register_logic_source`; a webhook, Slack, mail, MCP tool, or gated SQL write becomes an action target.

Read [docs/connections.md](connections.md) for the human story.

## Google ADK / Hermes

The same contract is emitted as `hermes_skill()` and `adk_function_tools()` from `tool_contract()`. Wire the kernel once; every agent surface agrees.
