# Layers: what the ontology needs vs what Palantir ships

Each layer has a job the twin cannot skip. Palantir already has a named service or product for almost all of them. Quinovo implements the **jobs**. Product names in the Palantir column are theirs (as of 2026).

**Stack**

| # | Layer | Palantir analog | Quinovo package (planned) |
|---|-------|-----------------|---------------------------|
| L0 | Substrate | Foundry storage/compute + Apollo | Borrow: Postgres, TSDB, blobs, NATS/Redpanda, OTel |
| L1 | Ontology language | OMS + Ontology Manager schema | `packages/language` |
| L2 | Funnel / sync | Object Data Funnel | `packages/funnel` |
| L3 | Object engine (reads) | Object databases + Object Set Service | `packages/engine` |
| L4 | Time series + media | Time series properties, attachments | `packages/series`, `packages/media` |
| L5 | Actions (writes) | Actions service | `packages/actions` |
| L6 | Functions runtime + typed inference | Functions on Objects | `packages/functions`, `packages/inference` |
| L7 | Dynamic security | Roles, Restricted Views, object/property policies | `packages/security` |
| L8 | Models + scenarios | Modeling stack, AIP Logic, Scenarios | `packages/models`, `packages/scenarios` |
| L9 | Toolchain | OSDK, Developer Console, OpenAPI, Ontology MCP | `packages/sdkgen`, `packages/mcp`, `packages/cli` |
| L10 | Operator surfaces | Ontology Manager, Object Views, Object Explorer | `apps/manager`, `apps/object-view` |
| L11 | Domain packs | Customer ontologies | `packs/homelab`, `packs/example-*` |

L0 is borrowed infrastructure. L1–L8 are the ontology. L9–L10 are how anyone besides the author uses it. L11 is the world, not the engine.

---

## L0 — Substrate

Not ontology. The mesh the ontology runs on.

**Needs**

- Durable datasets (backing rows for object types)
- Compute to index, run functions, score models
- Identity, network, secrets, observability
- A clock everyone agrees on (edit resolution and action timestamps)

**Palantir currently**

Foundry (datasets, Pipeline Builder, Transforms, lineage) plus Apollo (deploy/config across the mesh). Multipass users/groups, markings, Workspace shell. Edit-resolution docs assume UTC.

**Quinovo**

Postgres, a time-series store, object blobs, an event bus, OpenTelemetry. Do not clone Pipeline Builder, the lakehouse, or Apollo. Point Funnel at SQL / Parquet / Prometheus / Tailscale JSON.

---

## L1 — Ontology language (schema)

The categorization of the world. Palantir stores this in the **Ontology Metadata Service (OMS)**.

**Needs**

| Primitive | What you specify |
|-----------|------------------|
| Ontology | Name, owners, default timezone |
| Object type | apiName, primary key, title, description, status, backing dataset |
| Property | Type (string, int, enum, geo, struct), nullability, description, display |
| Shared property | Reuse `status`, `owner_id` across types so names do not drift |
| Link type | From/to, cardinality 1:1 / 1:n / n:n, apiNames on both sides |
| Interface | Shared shape + capabilities (`HasTelemetry`, `HasPresence`) |
| Action type | Parameters, submission criteria, rules, side effects — as schema, not as an app script |
| Function / query signatures | Inputs (object \| objectSet \| scalar), output, timeout, permissions |
| Roles on the schema | Who may edit types vs apply actions vs see a resource |
| Capabilities | Event start/end, geo, default time series, media — beyond columns |

**Palantir currently**

OMS is the metadata source of truth. Humans edit in **Ontology Manager**; code-first teams use **Ontology-as-code in a SuperRepo**. Object type ≈ dataset, object ≈ row. **No links across Ontologies.** Capabilities tab: event start/end, map tracks from lat/lon time series, default time series, media reference properties. Actions on interfaces (create/modify/delete “objects of interface”). Standing rule: do not sync every source table; types exist for decisions, in operators’ language.

**Compiler outputs Quinovo must emit from one schema**

JSON Schema + OpenAPI, SQL/migration plan (SAFE vs BREAKING), OpenFGA model, TypeScript + Python SDK stubs, MCP tool descriptors, markdown wiki of types (Graphify corpus).

---

## L2 — Funnel (datasets become objects; edits survive refresh)

Without this, the twin is a view that dies when the warehouse rebuilds, or a graveyard of operator edits that pipelines smash.

**Needs**

- Map each object type to backing datasources (batch and/or stream)
- Keep the index fresh as sources change
- Merge source rows with user/agent edits without silent clobber
- Persist edits independently of the index
- Lineage: every property value has `source_system`, `transform_sha`, `as_of`
- Wipe or migrate edits when the schema changes

**Palantir currently**

**Object Data Funnel** (Object Storage v2). Reads Foundry datasets, restricted views, and streaming datasources; indexes into object databases. Funnel batch plus Funnel streaming (seconds to minutes). After OSv1→v2 migration, the first Funnel pipeline can take ~30 minutes to start.

Per-datasource resolution: **Apply user edits** (default, edits-win) or **Apply most recent value** (UTC timestamp compare). Merged dataset is auto-built so the edit queue does not grow forever.

Indexed object data is treated as **ephemeral**. Source datasets are durable. User edits are stored persistently and folded into Funnel’s merged dataset. OSv1 used a **writeback dataset** per object type; OSv2 dropped that as the gate and uses optional materialized datasets for downstream consumers. OSv2 schema-migration framework includes “drop all edits” from Ontology Manager → Datasources → Edits.

This is the unsexy Palantir advantage: a plant operator can change a work-order status and survive tonight’s ERP extract.

---

## L3 — Object engine (reads)

Applications never query the backing dataset for live Ontology reads. They talk to an indexed object API.

**Needs**

- Load object by type + primary key, selected properties
- Filter, search, paginate
- Traverse **named** link types (`searchAround`), not ad-hoc joins
- Compose object sets: union, intersect, subtract
- Aggregate without dumping every row
- Polymorphism via interfaces (`asType` / `HasTelemetry`)
- Subscribe to object diffs (SSE/WebSocket)
- Honest materialization (index vs federate)

**Palantir currently**

**Object databases** store the index; **Object Set Service (OSS)** serves search, filter, aggregate, load. **Object Storage v2** replaced Phonograph (OSv1) to split indexing from querying; migration to OSv2 is mandatory. Object-set operations include union, intersect, subtract, searchAround, asType, interfaceBase. TypeScript OSDK `.subscribe` and WebSocket Ontology-change subscriptions. They **materialize**; they do not query the ERP in place. Freshness lag is the trade.

---

## L4 — Time series, events, media

An ontology with only scalar properties cannot be operational for machines, flights, or a home lab. The series is a **property of the object**, backed by a different store.

**Needs**

- A time series property type (pointer + store), not a million Event objects per sample
- Units, interpolation, a default series for “just plot this object”
- Sensor (one series) vs entity-with-many-series
- Events as objects with start/end, linkable onto series
- Media and geo as properties
- Windowed read API
- A defined write path for appending points

**Palantir currently**

**Time series properties (TSPs):** a string property holds series IDs; a **time series sync** (from Pipeline Builder) holds the points. Configured on the Capabilities tab. Primary key cannot be the TSP. Formatting (units, interpolation) can be static or point at other string properties. One **default TSP** (Quiver / Object View use it automatically). **Sensor object type:** exactly one TSP, must be default.

Events: Capabilities → Event start/end timestamps; Map/Vertex overlay events on tracks. Media reference properties (viewer in core Object View). Geospatial properties; track lat/lon as numeric TSPs.

Read API: Foundry API v2 `streamValues` on `/objects/{type}/{pk}/timeseries/{property}`. Python OSDK can pull dataframes.

**Gap:** Palantir currently does **not** support writing time series from Actions (including Scenarios). Workarounds: write a scalar or synthetic linked object; or mint a new series ID and point the TSP at it.

**Predictive ontology starts here.** A forecast is another series (or a `Forecast` object linked to the Device) with model lineage. Palantir binds models as properties/functions on the same object. There is no second “predictive OMS.”

---

## L5 — Actions (the verbs)

Palantir’s claim that this is not a semantic layer stands or falls here. An action is one transaction: parameters in, object/link edits plus side effects out, same logic in every app.

**Needs**

- Action type as a named, versioned verb (not “update row”)
- Parameters with types, defaults, object references
- Rules that compile to one edit per object
- Submission criteria (who + when this verb is legal)
- Side effects after (or before) commit
- One write path for humans and agents
- Decision lineage / undo
- Idempotency

**Palantir currently**

**Action types** in Ontology Manager. Example: `Assign Employee` changes `role` and creates a Manager link; HR-only submission criteria.

Rules: create / modify / create-or-modify / delete object; create/delete many-to-many links; **function rule** (exclusive — the function is the whole transaction); interface variants of the same. Invalid combos (delete before add) are rejected. Values from parameters, object-parameter properties, static values, current user/time.

Side effects: notifications (in-platform / email); webhooks (before or after edits); schedule rules that kick a Foundry build (edits apply after the build starts).

The **Actions service** applies edits; Funnel indexes them. OSDK `applyAction`, Workshop buttons, AIP Logic all hit the same type. OSv2 undo toast reverts the **most recent** action on an object. **Scenarios** apply actions in an overlay until commit.

**Quinovo will not allow:** generic PATCH of an object; direct TSP writes from an action without an explicit series-append action type; security only in the UI.

---

## L6 — Functions and inference (logic on objects)

Actions are the public verbs. Functions are the code those verbs, and the apps, call.

**Needs**

- Typed inputs: object, object set, scalar; typed outputs
- Read path: properties + `searchAround` inside a sandbox
- Write path: a function that returns a set of Ontology edits
- Isolation, timeout, no raw disk
- Streaming for long LLM calls
- Same function callable from UI, action, and agent

**Palantir currently**

**Functions on Objects** in TypeScript and Python, isolated server-side. Used for Workshop variables and function-backed columns, Quiver metrics, Slate, function-backed actions, AIP Logic (LLM-authored functions that still take/return Ontology objects). External functions call out. Python can run as a Pipeline Builder sidecar (batch, not operational). Streaming supported for incremental/real-time UX, especially language models. Language feature support differs; they publish a matrix.

**Split to keep:** simple actions stay declarative rules (create/modify/delete). Functions are for logic a form cannot express. Dumping everything into Python on day one recreates a backend with extra ceremony.

**Quinovo now:** pack `inference.yaml` is the first L6: typed rules over objects, named links, and forecasts. Conclusions are inferred facts with provenance and the same 80% HITL bar. A Python functions runtime still belongs here later; the graph is not the reasoner.

---

## L7 — Dynamic security

Palantir lists security as a **kinetic** element, not a gateway in front of the app. Policies are evaluated when a human or agent reads an object or submits an action. App-only filters do not count.

**Needs**

- Who can change the schema
- Who can read which object (row)
- Who can read which property (column/cell)
- Who can submit which action on which object (seeing ≠ restarting)
- Agent / SDK identity = app token ∩ caller ACL
- No linked-child leakage (child must carry parent ACL)
- Honesty about what happens after JSON leaves the API

**Palantir currently**

Ontology roles on the Ontology and on individual resources. **Restricted Views (RVs)** back object types with row-level policy (groups, markings, user-id-in-array), applied as a Funnel datasource. **Object security policies** + **property security policies** for cells (user must pass both). RVs were historically row-not-column; Cipher is a separate obfuscation path.

Developer Console app token scoped to selected object/action types **and** the calling user’s permissions. Palantir’s warning: RV/OSP filter **OSDK reads**; they do not follow the JSON into your app. Pair with markings/classification if data leaves Foundry.

Linked-object leakage is a documented footgun: bake the allowed-user array onto the child in the pipeline, then RV it. Do not filter only in a TypeScript function.

---

## L8 — Models, forecasts, scenarios

Palantir does not ship a second ontology for predictions. Models are Foundry assets. Outputs become properties, objects, or function returns on the same twin. Scenarios are a sandbox of uncommitted actions + model runs.

**Needs**

- A Model as an Ontology-visible asset (version, license, evals)
- Bind outputs onto the same object types operators already use
- Forecasts as series or as `Forecast` objects
- LLM logic that still speaks objects, not free text
- What-if without poisoning production
- Evals next to the number (`Forecast.skill_mae`)

**Palantir currently**

Models live in Foundry’s modeling stack. You publish a wrapper function around a deployment and call it from Workshop, Vertex, or an action. Older **Modeling Objectives** still appear in Vertex graphs. AIP Logic: no-code LLM functions whose inputs/outputs are Ontology objects, strings, or edits (“k-LLM”: models never get raw ungoverned tools).

**Scenarios** in Workshop/Vertex: apply actions in an overlay, inspect, commit or discard. Distinctive; most OSS clones skip it.

Because Actions cannot write TSPs, scenario-time forecasts often land on scalar properties or a synthetic linked object, with a function that prefers scenario data over the TSP.

TimesFM’s honest place: a Model behind a function — read `Device.cpu_pct` series → write `Device.cpu_pct_p90_4h` (or a `Forecast` object). Palantir would wrap that as a function-backed action or a scheduled Funnel job. It would not become its own layer.

**License:** TimesFM 3.0 weights are non-commercial / non-production. Quinovo’s default binder should use TimesFM 2.5 (Apache-2.0 weights) or another Apache-licensed model.

---

## L9 — Toolchain (the ontology as a backend)

Without this, you have a private database.

**Needs**

- Generated, typed client from the live schema
- Application registry and scoped tokens
- Agent protocol (tools are typed actions and object loads, not shell)
- Schema CI: breaking vs safe

**Palantir currently**

**OSDK:** npm TypeScript, pip/Conda Python, Maven Java, OpenAPI for everyone else. Generated from the subset of types the app is scoped to. Property descriptions surface in the editor. **Developer Console:** pick object types + action types, generate a versioned SDK, OAuth. **SuperRepo:** Ontology-as-code + app in one repo with local SDK regen. Subscribe to Ontology changes (TS OSDK / WebSocket). Ontology MCP / AIP agent toolchain. Evals are a platform capability set.

---

## L10 — Operator surfaces

**Needs**

- A place to edit the language
- A page per object instance (properties, links, series, actions)
- Search across types
- Optional app builder — not required for v0

**Palantir currently**

**Ontology Manager** (types, datasources, edits wipe, capabilities, actions). **Core Object Views** (generally available February 2026): auto-built from the type — properties, media, TSP charts, geo, linked objects. Custom Object Views still live in Workshop. **Object Explorer** for search. Then Workshop, Quiver, Vertex, Map, Slate — Toolchain products, not the Ontology kernel.

Quinovo v0: Manager CLI + one Object View. Skip Workshop-class builders.

---

## L11 — Domain packs

Not a Palantir product. Customers (and Palantir field teams) build the airline / hospital / plant ontology *in* OMS. The platform is domain-neutral.

**A pack must contain**

- Object / link / action / interface definitions
- Funnel connectors (Tailscale, node_exporter, ERP extract, …)
- Functions and model bindings for that domain
- Seed data and eval sentences (“`acknowledge_alert` is audited”)

**Palantir equivalent:** a customer Ontology in Ontology Manager + Pipeline Builder outputs as datasources + code repos / AIP Logic / modeling deployments attached to those types.

If `packages/engine` knows what a Jetson is, the design has already failed. Homelab types live in `packs/homelab`.
