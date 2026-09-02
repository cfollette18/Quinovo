# Quinovo

Quinovo **is an MCP server**. The tools are a Palantir-style operational ontology: typed objects, named links, inference, and governed actions. HTTP `quinovo serve` is a debug surface.

You bring the world as a **pack** (`ontology.yaml`, `inference.yaml`, `seed.yaml`, optional `security.yaml` and functions). Shop, hospital, factory, lab — the engine does not care. It never hard-codes your nouns. Load a different pack, get different types, links, and actions. Same binary.

This is **not** another GitHub knowledge graph. Objects and named links are storage. The product is **typed inference** on top: forecasts become facts, facts plus links become recommended actions, low-confidence conclusions wait for a human. Agents may only `apply_action`. They may not `PATCH` a row or run SQL.

Cursor, Claude, and Hermes (via MCP) are brains. Quinovo is the world. Google ADK wraps the same tools.

Read [research/taught-with-a-package.md](research/taught-with-a-package.md) (one teaching pack, not the product), then [research/inference.md](research/inference.md), then [research/plan.md](research/plan.md).

## Run

```bash
make test
# Product — point --pack at any world:
quinovo mcp --pack packs/example
# Cursor MCP config: command `quinovo`, args `mcp --pack <your-pack> --db .data/quinovo.sqlite`

# Copy a starter pack and rename the nouns:
quinovo init ./my-world
quinovo init --from clinic ./my-clinic

# Debug HTTP (not the public shape):
make dev
# Object View: http://127.0.0.1:8791/view/{Type}/{id}
# Schema:      http://127.0.0.1:8791/manager
```

MCP tools (generated against the loaded pack): `list_object_types`, `get_object`, `search_around`, `filter_objects`, `list_inferred_facts`, `run_inference`, `list_actions`, `apply_action`, `get_series`, `explain_fact`.

## Packs

A pack is a domain. Quinovo is not.

| Pack | Why it exists |
|------|----------------|
| `packs/example` | Teaching world (a box, a buyer, a shipper). Default for `quinovo init`. Copy it, rename the types. |
| `packs/clinic` | Honesty check: a second domain in the same binary. |
| `packs/homelab` | Personal dogfood. Not the brand. CI uses a checked-in fixture, never a live network. |

Interfaces and shared properties let packs share shape (`status`, `Trackable`) without a god type. Pack Python functions sit next to YAML rules. TimesFM 2.5 is the named forecast plugin; 3.0 weights stay off this path.

## Not the product

The teaching pack is how we explain inference. Your lab is how *you* dogfood. Neither is Quinovo. TimesFM and Graphify are optional plugins into forecast and schema-proposal layers.

## Status

Phases A–D: MCP tools generated from the **loaded pack**, Funnel overlay, HITL below 80%, more than one domain in CI, series + TimesFM 2.5 plugin, pack functions, OpenFGA-shaped security (type → row → property), unattended vs approval as a separate knob, generated Object View and schema manager, scenarios as an overlay, Postgres as a dialect helper — not a lakehouse.
