# Quinovo

An **operational ontology**. Typed objects, named links, inference, and governed actions. Agents talk to it over MCP. They may only `apply_action`. They may not `PATCH` a row or run SQL.

You bring the world as a **pack**. The engine does not know your nouns.

![Quinovo ontology](docs/hero.png)

[![Demo: objects, links, inference, apply_action](docs/demo.gif)](docs/demo.mp4)

[Watch the demo (mp4)](docs/demo.mp4)

## Four primitives

If any one is missing, you built something else.

| Primitive | Job | If missing, you built |
|-----------|-----|------------------------|
| **Data** | Objects, properties, named links, series | A wiki |
| **Logic** | Rules, functions, forecasts, inference | Pretty CRUD |
| **Action** | Named transactions — the only legal writes | A read-only graph |
| **Security** | Type, row, and property, evaluated at call time | An agent with root |

![Four primitives](docs/primitives.svg)

![Data, logic, action, security](docs/four-primitives.png)

## How a write happens

Objects and named links are storage. The product is **typed inference** on top: forecasts become facts, facts plus links become recommended actions, low-confidence conclusions wait for a human.

![From graph to apply_action](docs/flow.svg)

![Inference on the twin](docs/inference.png)

The teaching pack is a box, a buyer, and a shipper. Late forecast → `at_risk` → `notify_buyer`. Below 80% confidence the fact stays pending. `apply_action` is the only write, and it is audited.

## Run

```bash
make test
quinovo serve
quinovo mcp --pack packs/example
quinovo init ./my-world
quinovo init --from clinic ./my-clinic
```

MCP tools are generated from the loaded pack. An agent's session is three calls: `briefing` at the start (one page of what is live), `about(name)` or `recall(query)` before answering, and `save_turn` at the end with the turn's facts as subject–predicate–value triples, decisions, todos, questions, and memories. The rest — `get_object`, `search_around`, `filter_objects`, `list_inferred_facts`, `apply_action`, `propose_rule`, and so on — is paged and filterable.

Quinovo ticks itself in the background — it pulls sources, extracts entities and triples from new turns with the configured model, infers, and applies unattended actions. Agents never need to be told "quinovo tick".

The workspace rail includes **Train**: filter live things, connections, noticed facts, and changes into a named set, then prepare a **small specialist** job. That writes a JSONL file under `.data/train/` — it does not run a GPU trainer unless you point `QUINOVO_TRAIN_CMD` at one. The Settings language model stays a separate authoring path.

## Packs

A pack is a domain. Quinovo is not.

| Pack | Why it exists |
|------|----------------|
| `packs/example` | Teaching world. Default for `quinovo init`. Copy it, rename the types. |
| `packs/clinic` | Honesty check: a second domain in the same binary. |

Read [docs/ontology.md](docs/ontology.md).

## Why Quinovo

An operational ontology is the nouns and verbs of a business. Quinovo makes a different bet than the closed, consultant-driven approach:

1. **Discovered, not hand-built.** The model proposes the types, rules, and actions from your live data. You only approve.
2. **MCP is the connector layer.** No proprietary marketplace. Any MCP-compatible client reads and writes the ontology; Quinovo also exposes itself as MCP.
3. **Small specialists, not one giant model.** Filter the ontology into a dataset and train a small specialist on just your data (the Train tab).
4. **HITL is the only human job.** The loop runs itself; below 0.8 parks for review, 0.8+ auto-applies.
5. **Open source.** Apache-2.0. The kernel is yours.
6. **Security is a primitive.** Data, Logic, Action, Security — security is first-class in the kernel.

Read [docs/why-quinovo.md](docs/why-quinovo.md) and [docs/sdk.md](docs/sdk.md).

## Connectors, logic, and systems of action

- **Data flows in** through `register_source` / `pull_source` / `POST /ingest/{source}` (http, json, csv, webhook, sql, mcp). The connector layer is MCP — not a marketplace of hundreds of adapters.
- **Logic lives anywhere** through `register_logic_source` / `run_logic_source` (http). Logic does not have to live in YAML rules.
- **Actions write back** through `register_action_target` (webhook, slack, email, mcp, gated sql). Applying an action drives a real change in an external system, audited. Failures never undo the local apply.
- **LLM reasons over the ontology** through `propose_action` — propose applying a named action with confidence; HITL below 0.8.

Apache-2.0.
