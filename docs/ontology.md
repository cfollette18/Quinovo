# What Quinovo means by ontology

Quinovo is an **operational layer** on top of whatever digital assets you already have. It holds both the **semantic** pieces (objects, properties, links) and the **kinetic** pieces (actions, functions, security evaluated at call time).

It is **not** a graph database, a metrics semantic layer, a catalog, a file indexer, or a forecasting model. Those can feed Quinovo. They are not Quinovo.

It **is** a typed API of a world: nouns you can load and traverse, verbs you can submit, logic that runs against those nouns, and security that applies to both humans and agents.

## Four primitives

| Primitive | Job | If missing, you built |
|-----------|-----|------------------------|
| **Data** | Objects, properties, named links, time series | A wiki |
| **Logic** | Functions, rules, models that read the twin | Pretty CRUD |
| **Action** | Governed transactions that edit objects | A read-only graph |
| **Security** | Who can see which object and fire which action | An agent with root |

## Language, engine, toolchain

1. **Language** — object types, links, properties, actions, and the logic that defines how actions operate.
2. **Engine** — reads (object-set queries) and writes (atomic, named actions only).
3. **Toolchain** — MCP today; generated views and a pack you can copy.

## Dataset analogy (teaching only)

| Tables | Ontology |
|--------|----------|
| Table | Object type |
| Row | Object |
| Column | Property |
| Cell | Property value |
| Join | Named link type |

The product starts when those rows are **indexed**, **traversable by named links**, **writable only through actions**, and **permissioned as objects**.

## Design rules

- The ontology is an **API**. Do not sync every source table as a type.
- Types and actions must support **decisions**, in operators' language.
- Isolated objects (no links) are a smell. Unnamed links are a smell.
- The engine is domain-neutral. Packs carry the world.

The v0 that counts: language + object-set reads + governed actions + one pack with a few types, named links, and one audited action. If a release cannot say “the only way to close this is `apply_action`, and it is audited,” it is a knowledge graph, not Quinovo.
