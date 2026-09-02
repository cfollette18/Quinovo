# Agents: Hermes, Google ADK, and anything else

Quinovo **is** an MCP server (`quinovo mcp`). Hermes, Google’s Agent Development Kit (ADK), Cursor, and Claude are brains. They must not get a database handle.

## Contract

Generated from the ontology (L1), every runtime gets the same three tool families:

1. **Read** — `list_object_types`, `get_object`, `search_around`, `filter_objects`, `get_series`
2. **Infer** — `run_inference`, `list_inferred_facts` (asserted only for unattended agents)
3. **Act** — `list_actions`, `apply_action` (never PATCH)
4. **Propose** (optional, gated) — `propose_object_type`, `propose_connector` — writes a *draft pack*, does not mutate live objects until a human or `apply_action(publish_schema)` lands

Auth: tool token ∩ user/robot role (L7). Audit: every `apply_action` (L5).

## Adapters (same tools, different SDKs)

| Runtime | Adapter |
|---------|---------|
| MCP | Native. `quinovo mcp` stdio (Streamable HTTP later) |
| Hermes | Plugin/skill whose tools call the Quinovo API |
| Google ADK | `FunctionTool` wrappers generated from OpenAPI |
| Python/TS apps | Generated OSDK-style client |

When L1 gains `Warehouse`, all three adapters gain `get_object(Warehouse, …)` on the next generate. That is “AI throughout” without a special case per agent kit.

## Automation loop (no human in the inner cycle)

1. Funnel syncs sources on a schedule (L2).
2. Inference refreshes deduced facts from forecasts and typed links (L6). Models write forecasts onto objects (L8).
3. An agent (Hermes or ADK) is woken by “Package.eta_p90 slipped.”
4. It may only `apply_action(notify_buyer)` or `apply_action(mark_delivered)` if submission criteria allow unattended use.
5. Destructive or novel actions wait for a human.

Unattended vs approval is **per action type**, not a chatbot setting.

## What we will not do

- Let the model emit raw SQL or shell against the store.
- Ship a Quinovo-only agent that competes with Hermes/ADK. We integrate.
- Require one vendor LLM. The ontology is the lock-in we want; the brain is swappable.
