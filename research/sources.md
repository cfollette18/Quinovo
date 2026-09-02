# Sources

Research compiled 2 Sep 2026 for Quinovo. Palantir product behavior is from public docs and community posts, not from a Foundry enrollment.

## Palantir (public)

- [Ontology overview](https://www.palantir.com/docs/foundry/ontology/overview/) — operational layer; semantics vs kinetics.
- [Core concepts](https://www.palantir.com/docs/foundry/ontology/core-concepts/) — object / property / link / action; dataset analogy.
- [The Ontology system](https://palantir.com/docs/foundry/architecture-center/ontology-system/) — data + logic + action + security; Language / Engine / Toolchain.
- [Object backend overview](https://palantir.com/docs/foundry/object-backend/overview/) — OMS, object databases, OSS, Actions, Funnel, Functions on Objects; OSv1 Phonograph vs OSv2.
- [OSv1 → OSv2 migration](https://palantir.com/docs/foundry/object-backend/osv1-osv2-migration/)
- [How user edits are applied](https://palantir.com/docs/foundry/object-edits/how-edits-applied/) — edits-win vs most-recent; merged dataset; drop-all-edits.
- [Action types overview](https://www.palantir.com/docs/foundry/action-types/overview/)
- [Action type rules](https://www.palantir.com/docs/foundry/action-types/rules/)
- [Functions overview](https://www.palantir.com/docs/foundry/functions/overview/)
- [Time series properties](https://www.palantir.com/docs/foundry/time-series/time-series-properties/)
- [TSP use case (Ontology Manager)](https://palantir.com/docs/foundry/time-series/time-series-properties-use-case-ontology/)
- [Ontology SDK overview](https://www.palantir.com/docs/foundry/ontology-sdk/overview/)
- [palantir/osdk-ts](https://github.com/palantir/osdk-ts/)
- [Ontology and pipeline design principles](https://community.palantir.com/t/ontology-and-pipeline-design-principles/5481/1)
- [TSP writes from actions / scenarios](https://community.palantir.com/t/how-do-i-update-a-time-series-property-in-an-object-using-an-action-to-run-a-model-in-vertex/3659) — Actions cannot write TSPs.
- Core Object Views GA — Foundry announcements, February 2026.
- Akshay Krishnaswamy, *Connecting AI to Decisions with the Palantir Ontology* (Palantir architecture PDF).

Secondary synthesis (not primary): [PuppyGraph — Palantir Ontology architecture](https://www.puppygraph.com/blog/palantir-ontology).

## Tools in scope

- [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)
- [google-research/timesfm](https://github.com/google-research/timesfm) — 2.5 Apache-2.0 weights; 3.0 non-commercial/non-production weights.

## OSS analogs

- [syzygyhack/open-foundry](https://github.com/syzygyhack/open-foundry)
- [AlbertLee1/Weave](https://github.com/AlbertLee1/Weave)
- [getzep/graphiti](https://github.com/getzep/graphiti)

## Local (this machine, not in this repo)

- `~/fleet-plan.md` — Portage mesh; Graphify + TimesFM parked at v0.6+ on pi5.
- `~/pi5/README.md` — Pi 5 as data-collection node.
- `~/jetson-heater/README.md` — heater Orin stack.
- Tailscale census, 2 Sep 2026 — local only, not in this tree.
