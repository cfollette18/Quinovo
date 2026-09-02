# Acceptance: “similar to Palantir”

A Quinovo release is Palantir-like when these sentences are true in software, not in a README. Layers in parentheses.

| Sentence | Layers |
|----------|--------|
| A Package is a typed object; it contains a Product, is destined_for a Person, shipped_by a Company. | L1 L3 |
| A late forecast on that Package infers `at_risk`, then `notify_buyer` naming Bob — not a generic graph hop. | L4 L6 L8 |
| An agent asks “what is Bob waiting on?” via searchAround, not SQL. | L3 L9 |
| `mark_delivered` is the only way to close a Package; it is audited; MCP cannot PATCH the row. | L5 L7 L9 |
| A function can traverse Package → Person and return “Bob’s open orders.” | L6 |
| A second pack (homelab devices, or a clinic) loads without forking the engine. | L11 |

If a release only stores nodes and edges, it is a knowledge graph. If it cannot pass the action-audit sentence, it is still not Quinovo.

## Suggested build order

Canonical sequence is [plan.md](plan.md) (phases A–D). Short map:

| Phase | Ship |
|-------|------|
| Now | Language + objects + links + `mark_delivered` + HITL classify/types + forecasts + typed inference on `packs/example`. |
| A | Generated MCP/OpenAPI, `notify_buyer`, Funnel edit overlay, asserted-only auto-act. |
| B | Interfaces, `packs/homelab`, `quinovo init`, Hermes/ADK, propose-types. |
| C | Provenance, series on objects, TimesFM 2.5 plugin, Python functions. |
| D | OpenFGA, Object View, schema manager, Postgres if needed, scenarios last. |

## Hardware placement (homelab pack)

| Component | Where | Why |
|-----------|-------|-----|
| Object store + TSDB writer | pi5 once on tailnet; heater only as temporary if pi5 stays absent | xtal sleeps |
| Graphify index | xtal when open; copy `graph.json` to pi5 | LLM extraction is heavy |
| TimesFM inference | pi5 CPU or spare GPU; never beside llama-server on 8GB Orin | heater RAM is the binding constraint |
| Collectors | each `class=lab` Device | Push over Tailscale; spool on disconnect |
