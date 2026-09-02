# What Quinovo means by ontology

Palantir’s public definition is the one Quinovo copies as a *job*, not as a product:

> The Palantir Ontology is an operational layer for the organization. It sits on top of the digital assets integrated into the platform (datasets, virtual tables, and models) and contains both the **semantic** elements (objects, properties, links) and the **kinetic** elements (actions, functions, dynamic security).

An ontology in this sense is **not**:

- a graph database (Neo4j, Graphiti)
- a metrics semantic layer (dbt Semantic Layer, Cube)
- a catalog (Unity Catalog)
- a file-to-graph indexer (Graphify)
- a forecasting model (TimesFM)

Those can feed or sit beside Quinovo. They are not Quinovo.

It **is** a typed API of a world: nouns you can load and traverse, verbs you can submit, logic that runs against those nouns, and security evaluated at call time for both humans and agents.

## Four primitives (must all exist)

Palantir’s architecture center describes a four-fold integration. If any one is missing, the thing you built has a different name.

| Primitive | Job | If missing, you built |
|-----------|-----|------------------------|
| **Data** | Objects, properties, links, time series, attachments — the digital twin | A wiki or a knowledge graph |
| **Logic** | Functions, rules, models, LLM calls that read the twin | A CRUD API with pretty names |
| **Action** | Governed transactions that edit objects and write back to the world | A read-only semantic layer |
| **Security** | Who can see which object/property and who can fire which action, at call time | An agent with root |

## Palantir’s three system groups

The Ontology is “not a thin semantic layer.” Palantir groups dozens of components into:

1. **Language** — object types, links, properties, actions, automations, and the logic that defines how actions operate.
2. **Engine** — read architecture (SQL-scale queries, subscriptions, materializations) and write architecture (atomic transactions, batch mutations, streams, CDC).
3. **Toolchain** — OSDK, DevOps, UIs, so developers treat the Ontology as a backend.

Quinovo’s numbered layers (L0–L11) are that split made implementable as packages. See [layers.md](layers.md).

## Dataset analogy (Palantir core concepts)

| Dataset world | Ontology world |
|---------------|----------------|
| Dataset | Object type |
| Row | Object (instance) |
| Column | Property |
| Cell | Property value |
| Join | Link type |

The analogy is a teaching tool, not the product. The product starts when those rows are **indexed**, **traversable by named links**, **writable only through actions**, and **permissioned** as objects rather than tables.

## Design rules (Palantir, adopted)

- The ontology is an **API**. Maintain it. Do not sync every source table as an object type.
- Object types and actions must support **decisions**, in operators’ language. If you cannot say a natural-language sentence with the types, the types are wrong.
- Isolated objects (no links) are a smell. Unnamed links (`Object2`) are a smell.
- Shared, company-wide (here: pack-wide) types beat per-app snowflakes.

## Quinovo’s stance

- **Engine** is domain-neutral (`packages/*`).
- **Packs** carry the world (`packs/homelab`, later `packs/example-supply-chain`).
- Graphify indexes the language and pack docs for agents. It does not store live objects.
- TimesFM is a Model implementation in L8. Forecasts bind as properties on existing objects.

The v0 that counts: language compiler + object-set reads + governed actions + OpenAPI + one pack with three object types, two links, and one audited action. If a release cannot say “the only way to close an Alert is `acknowledge_alert`, and it is audited,” it is a knowledge graph, not Quinovo.
