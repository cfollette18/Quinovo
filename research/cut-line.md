# Cut line: copy, skip, replace

Foundry is a platform. Quinovo is an ontology kernel plus packs. Cloning Workshop, the lakehouse, or Apollo is how this repo dies.

## Copy the ideas

| Foundry capability | Why |
|--------------------|-----|
| Language + Engine + generated SDK + Actions + security | This is Quinovo |
| Object Data Funnel over *some* backing store | Same job, smaller substrate (SQL/JSON/streams, not a proprietary lake) |
| Time series as object properties + model binding | Required for a predictive ontology |
| Decision lineage (action audit) | Palantir’s compounding trick |
| Interfaces | Packs share queries without a god object type |
| Read-time row/property policy | Agents otherwise leak |

## Copy later (hard, distinctive)

| Capability | Note |
|------------|------|
| Scenarios / what-if overlays | Do not fake with a second database. Defer until actions work. |
| Full object/property security policies | v0: type-level roles. v1: OpenFGA row + property redact. |
| Function-backed actions as the exclusive rule | After declarative create/modify/delete works |

## Replace

| Foundry | Quinovo |
|---------|---------|
| Pipeline Builder, Transforms, virtual tables | Connectors: SQL, Kafka, Prometheus, Tailscale JSON |
| AIP Logic no-code LLM builder | MCP + Functions. Graphify for schema RAG |
| Restricted Views as Foundry datasets | Funnel-time filter or query-time OpenFGA; pick one and document it |
| Writeback datasets (OSv1) | Edit overlay + merged table, OSv2-style |

## Skip

Pipeline Builder UI, Workshop, Quiver, Vertex, Contour, Slate, Map, Apollo, Gotham-style geospatial/intel apps, Cipher, enrollment markings theater, marketplace.

Object View + SDK is enough for a v0 that is Palantir-*like*. A pretty dashboard on a weak action pipeline is every other digital-twin demo.

## Existing OSS — steal boundaries, do not fork blindly

| Project | Useful boundary | Gap vs Palantir / Quinovo |
|---------|-----------------|---------------------------|
| [syzygyhack/open-foundry](https://github.com/syzygyhack/open-foundry) | ODL → GraphQL/REST/OpenFGA/SDK; actions as the only mutation path; domain packs | Healthcare-flavored; TSDB/models/scenarios thin |
| [AlbertLee1/Weave](https://github.com/AlbertLee1/Weave) | Go object sets + `applyAction`; Postgres + search + NATS | Single-machine; thinner pack/security story |
| [getzep/graphiti](https://github.com/getzep/graphiti) | Temporal facts + provenance for agents | Learned knowledge graph, not typed inference on objects/actions |
| dbt Semantic Layer / Cube | Metrics consistency | Read-only. No objects-as-API, no verbs |

## Legal

Do not ship as Foundry, OSDK, AIP, or Ontology Manager in a way that implies affiliation. Describe Quinovo as an operational ontology (objects, links, actions, functions). Apache-2.0 the code. Keep TimesFM 3.0 weights off the default path ([graphify-timesfm.md](graphify-timesfm.md)).
