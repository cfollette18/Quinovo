# Quinovo plan

This is the product plan. Layers and Palantir mapping live in [layers.md](layers.md). This file is **what we build, in what order, and what we refuse**.

Quinovo is domain-blind. Anyone loads their world as a **pack**. One teaching pack (`packs/example`) uses a box, a buyer, and a shipper so the loop is easy to read. That story is not the product. The engine does not know those nouns — or a hospital, or a lab.

## What it is

Quinovo is an open-source **operational ontology kernel**. The pack names the types. The engine runs them.

Four primitives, all required:

| Primitive | Job (in any pack) |
|-----------|-------------------|
| **Data** | Typed objects and named links the pack defines |
| **Logic** | Typed inference and functions/models on those objects |
| **Action** | Named verbs — the only writes |
| **Security** | Who may see an object, who may run an action, evaluated at call time |

A knowledge graph is Data with a query API. Quinovo is Data + Logic + Action + Security, with Logic as the product and the graph as storage.

System split (Palantir’s, kept): **Language / Engine / Toolchain**. Packs are not a fourth engine. They are L11: the world.

## North star (software, not README)

A stranger can:

1. `make test` with `packs/example`. No live network. No GPU. The engine source does not name a customer's nodes.
2. In that teaching pack: a Package contains a product, is destined for a person, is shipped by a company.
3. Write a forecast on that object, run inference, get a typed fact and a recommended action.
4. Connect Cursor (or any MCP client) via `quinovo mcp --pack …`. The model cannot PATCH a row.
5. Copy the pack, rename the nouns, load it in the same binary. A second pack in CI proves that is not a slogan.

You can point that same binary at `packs/homelab` and see xtal/heater as objects. That proves the framework. It is not the brand.

## Architecture (stable)

```
packs/<world>/          Language as YAML (+ later as-code)
  ontology.yaml         object / link / action types
  inference.yaml        typed rules (not SPARQL)
  seed.yaml             observed facts for make dev
  connectors/           Funnel sources (later)

src/quinovo/            Engine: domain-blind
  language/             compile schema → OpenAPI, MCP, FGA (later)
  funnel/               sources → objects; edits survive refresh
  engine/               objects, links, series, forecasts, inferred facts
  inference/            reasoner over types (the product)
  actions/              named verbs + audit
  ai/                   classify / propose types / HITL (80% bar)
  policy/               confidence + later OpenFGA
  mcp/                  THE product: generated tools over the kernel
  api/ + cli            quinovo mcp (stdio); serve is debug HTTP

Hermes / Google ADK later wrap the same MCP tools. Do not ship a Quinovo-only agent.
apps/                   Object View + schema manager (generated, not Workshop)
```

**Agents are brains. Quinovo is the world.** Same three tool families on every runtime: read typed links, run inference, apply named actions. Propose-schema is a fourth, gated family.

**HITL:** confidence `< 0.8` parks type definition, classification, inferred facts, and acting on forecasts. `≥ 0.8` auto-applies. Unattended vs approval for **actions** is a separate per-action flag (later). Do not mix those two knobs.

**Provenance:** `observed` (Funnel/seed) ≠ `inferred` (rules) ≠ `predicted` (models) ≠ `classified` (type assignment). Mixing them is how graphs lie.

**Plugins, not the kernel:** Graphify proposes types / indexes pack docs. TimesFM 2.5 writes forecasts onto objects. TimesFM 3.0 weights stay off the default path.

## Where we are (2026-09-02)

Shipped:

- **A.** MCP is the product (`quinovo mcp`). Funnel overlay. `notify_buyer` gated on asserted inference. HITL below 80%; approve re-chains.
- **B.** Interfaces + shared properties. `packs/homelab` (fixture connector) and `packs/clinic`. `quinovo init` copies example. Propose-types HITL. Hermes/ADK adapters over the same tools.
- **C.** `property_fact` + `join_links`, provenance traces, series on objects, TimesFM 2.5 plugin (3.0 refused), pack functions (`bobs_open_orders`).
- **D.** OpenFGA-shaped YAML (type → row → property). Per-action unattended vs approval. Generated Object View + schema manager. Scenarios as overlay. Postgres dialect helper, SQLite default.

`make test` never needs a tailnet or a GPU. Same binary loads `packs/clinic` and `packs/homelab`.

## Build in four phases

Phases A–D below are the map. They are implemented.

### Phase A — Close the loop

**Goal:** Amazon dump → objects → inference → agent tool → audited action, without PATCH.

| Slice | Why |
|-------|-----|
| Generated MCP (and OpenAPI) from L1 | Cursor/Hermes can touch the world. Same tools: `get_object`, `search_around`, `run_inference`, `list_inferred_facts`, `apply_action`. No SQL tool. |
| `notify_buyer` action | Inference currently stops at a string. The product is a verb. HITL if the triggering fact is pending. |
| Funnel edit overlay | Reloading seed / a dump must not un-deliver `1Z999` or drop inferred-asserted facts unless the pack says so. |
| Inference → action policy | Agents auto-`apply_action` only on **asserted** facts and **actionable** forecasts. Pending stays a proposal. |
| Thin Python client | One client the MCP adapter calls. Do not grow a second API. |

**Exit:** `make test` includes: forecast → infer → MCP-shaped tool list → `notify_buyer` audited. README still never mentions heater.

### Phase B — Anyone’s world

**Goal:** the honesty check. Engine still does not know Jetson.

| Slice | Why |
|-------|-----|
| Language: interfaces, shared properties, richer action rules | Packs share `HasTracking` / `status` without a god type. Actions: create / modify / delete plus parameter validation. |
| `packs/homelab` | Device / Service / Person; Tailscale connector; `acknowledge_alert`. Dogfood only. |
| `quinovo init --pack` | Stranger copies example, not homelab. |
| Propose-ontology (HITL) from files | Graphify or a simpler extractor proposes types. Human or ≥80% applies. Does not write live objects into `graph.json`. |
| Hermes + Google ADK adapters | Same tool schema as MCP. We do not ship a Quinovo-only agent. |

**Exit:** CI runs example pack. Optional integration job runs homelab fixtures (checked-in JSON), never live Tailscale in CI.

### Phase C — Real inference

**Goal:** YAML rules are the teaching reasoner. Production logic is functions + models on object types.

| Slice | Why |
|-------|-----|
| More rule kinds + provenance trace | `property_fact`, join two links, “why is this at_risk?” returns the forecast id + `buyer` link. |
| HITL approve re-runs the chain | Approving `at_risk` must be allowed to fire `notify_buyer` recommendation. |
| Time series properties (L4) | Scan events live **on** Package, not as a million objects. |
| Model registry + TimesFM 2.5 plugin | Forecasts are properties (or linked Forecast objects) with model id + as_of + skill. Default weights: 2.5. |
| Functions on Objects (Python) | Sandboxed: inputs objects/object-sets, outputs scalars, facts, or **action drafts**. No disk, no raw SQL. YAML rules stay for packs that do not need code. |

**Exit:** “Bob’s lipstick is likely late” is a forecast on Package plus a deduced fact, not a chatbot guess. A pack function can replace a YAML rule without forking the engine.

### Phase D — Governed production ontology

**Goal:** agents are not root. Humans get a generated view, not a custom app per domain.

| Slice | Why |
|-------|-----|
| OpenFGA: type, then row, then property | Seeing a Package ≠ marking it delivered. Agent token ∩ user. |
| Per-action unattended vs approval | Separate from the 80% AI bar. |
| Generated Object View | Package page: lipstick, Bob, Amazon, chart, inferred facts, **Mark delivered**. That button *is* the action. |
| Schema manager | Edit types as YAML/UI. Not Workshop, Quiver, Vertex. |
| Subscriptions / object sets at SQL scale | When SQLite object-set filters lie. Postgres as substrate, still not a lakehouse. |
| Scenarios | What-if overlay on the same types. Last, not a second database. |

**Exit:** a hospital pack and the example pack both run; an agent with warehouse role cannot mark Bob’s neighbor’s package delivered.

## What we will not build

- Neo4j + chatbot, GraphRAG-as-product, OWL theater with no verbs
- Foundry / Workshop / Apollo / Gotham clones or those names as ours
- Graphify or TimesFM inside `packages/engine`
- Homelab as the GitHub identity
- Agent `PATCH` / SQL / shell against the store
- TimesFM 3.0 as the default model path
- Starting over in Go/TS to look like Weave or open-foundry. Steal boundaries; keep this kernel.

## GitHub shape (when you ask to publish)

- Apache-2.0
- `packs/example` is the screenshot. Homelab is `packs/homelab` with a warning: personal lab, not the framework.
- `make test` / `make dev` on a laptop
- Docs path: taught-with-a-package → inference → this plan → agents
- No Palantir affiliation in README

## Working rule

If a slice does not make a true sentence about Package / Bob / Amazon **or** prove a second pack loads, it is not next. Infrastructure (Postgres, NATS, pretty dashboards) waits until the loop is closed.
