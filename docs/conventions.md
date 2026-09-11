# Conventions

The consistency contract for Quinovo. One word per concept, one name per field, one
shape per reference — used identically in code identifiers, pack YAML keys, MCP tool
names and descriptions, REST routes and JSON keys, UI labels, and prose.

If you are changing code and this file disagrees with the code, the code is wrong
until the rework lands; after that, this file is wrong only via a conscious edit here.

---

## Product vocabulary

The four primitives — **Data, Logic, Action, Security** — are chapter language.
Everything concrete maps to the terms below. Banned synonyms must not appear in
`src/`, `packs/`, `docs/`, or `README.md` (this table excepted).

| Canonical term | Meaning | Banned synonyms |
|---|---|---|
| **pack** | A domain bundle: the YAML files + functions that describe a world | world, domain (as a noun for the bundle) |
| **object type** / **object** | A typed thing, and an instance of it | entity, node, row, thing |
| **link** / **link type** | A named relationship between two objects | edge, relationship, connection |
| **action** / **action type** | A governed named write — the only legal write | verb, command, task (as identifiers) |
| **fact** | A machine-made conclusion with rule, confidence, provenance | conclusion, assertion (as nouns) |
| **forecast** | A predicted metric value with horizon + uncertainty band | prediction (the stored thing; `predicted` survives only as a provenance kind) |
| **rule** | A pack inference rule that fires facts | — |
| **source** | A registered data inlet (an instance) | integration; **connector** is only a source's *kind* (synthetic, csv, http, sql, mcp), never the instance |
| **logic source** | An external function/endpoint producing facts or forecasts | — |
| **action target** | A write-back endpoint bound to an action type | — |
| **hook** | An event-triggered outbound call or action | — |
| **proposal** | A suggested pack/type/rule/action change | suggestion |
| **tick** | One pass of the loop | cycle, iteration |
| **loop** | The autonomous runtime that ticks | engine (reserved for the storage subpackage) |
| **workspace** | The web UI as a whole | console, dashboard |
| **chat** | The workspace home — ask the ontology in plain language | twin (as a page), graph (as a page) |
| **scenario** | A what-if overlay on live objects | sandbox, draft |
| **series** / **metric** | Time-ordered points on an object / the measured quantity | stream, signal |
| **kernel** | The orchestrator object | — |
| **store** | The persistence layer | db, database (as a code concept) |
| **review queue** | Pending facts/proposals/actions awaiting a human | HITL (user-facing text; fine in internals) |

## Workspace rail

Rail order and routes agree with labels:

| Label | Route | Purpose |
|---|---|---|
| Chat | `/chat` | Ask the ontology — workspace home (public marketing stays at `/`) |
| Catalog | `/catalog` | Object types, rules, actions defined by the pack |
| Inference | `/inference` | Facts and the review queue |
| Sources | `/sources` | Data inlets, logic sources, action targets |
| Audit | `/audit` | The audit trail |
| Train | `/train` | Filtered sets → specialist training jobs |
| Settings | `/settings` | Workspace settings |

## Field and identifier naming

- **Object identity: `id`.** MCP params, REST paths and bodies, payload keys,
  dataclass fields, and DB columns all use `id` (`from_id`, `to_id`, `object_id`
  where qualified). Not `pk`, `primary_key`, or `object_pk`.
- **Facts.** The DB table is `inferred_facts`; every JSON key is `facts`.
- **Forecasts.** Object payloads nest them under `forecasts`; the forecast
  timestamp is `as_of`. Every other timestamp is `created_at`.
- **Links.** Graph JSON emits `links` with `{link_type, from_id, to_id}`.
- **Object references.** One canonical shape: `{"type": "Package", "id": "box-1"}`
  (the `ObjectRef` model). Used by action params, `security.yaml` bindings, and
  fact values. The composite string `Package:box-1` exists only as a UI label.
- **Actions.** Always `action_type` for the name of the verb.
- **Auto flags.** Sources and logic sources both use `auto: true`.
- **Proposal kinds** come from one shared registry; MCP tool params never shadow
  Python builtins.
- **Pack YAML.** Link types declare `from_type` / `to_type`. Seed links use
  `from_id` / `to_id`. Object types are PascalCase; link types, action types,
  rules, and properties are snake_case. `title_property` defaults to `name`.
  Property names are never Python keywords.
- **Confidence.** The auto-apply threshold lives in exactly one constant,
  `DEFAULT_AUTO_APPLY_MIN_CONFIDENCE` (`policy.py`); packs may override it in
  `ontology.yaml`; MCP instructions interpolate the live value. A rule's
  confidence is `confidence: float | None` plus optional `confidence_from`
  (e.g. `"forecast"`) — no sentinel strings in numeric fields.

## Lifecycle states

- **Facts:** `pending` → `asserted` | `rejected`; `asserted` → `retracted` when
  its premises no longer hold.
- **Proposals:** `pending` → `approved` | `rejected` | `auto_applied`.
- **Pending actions:** `pending` → `approved` → `applied`, or `pending` → `rejected`.

## Events

Event names are past-tense and dot-namespaced: `object.upserted`,
`object.deleted`, `link.set`, `link.removed`, `series.appended`,
`forecast.written`, `fact.asserted`, `fact.pending`, `fact.retracted`,
`action.applied`, `source.pulled`, `tick.completed`.

Every event carries `{name, created_at, actor, object_ref, detail}` where
`object_ref` is the canonical `{"type", "id"}` shape (null when not applicable).

## Layers

- **kernel** orchestrates; it never renders HTML and never speaks SQL.
- **store** (`engine/`) persists; it never decides policy.
- **payloads** (`engine/payloads.py`) is the only place records become JSON —
  no inline response dicts elsewhere.
- **api/** and **mcp/** are transport; they translate, they don't compute.
- **apps/** renders; it reads through the kernel's data endpoints.
- The loop (`loop/`) reacts to events; polling intervals are safety nets, never
  the driver.
