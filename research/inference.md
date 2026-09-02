# Inference is the product. The graph is just storage.

A knowledge graph stores **what was already said**: Package `1Z999` contains lipstick, is destined for Bob, is shipped by Amazon. GitHub is full of those. Quinovo has one too (objects + named links). That is L3 storage, not the point.

**Inference** is new truth the dump never contained:

| Kind | Example | Provenance |
|------|---------|------------|
| **Deduction** | Package is at_risk **because** it has a buyer **and** a late forecast | `inferred` |
| **Prediction** | `late_risk = 0.31` in 24h (TimesFM / any model) | `predicted` |
| **Classification** | This row is a Package at 92% | `classified` (HITL if < 80%) |
| **Link invention** | Tracking `1Z…` ⇒ `shipped_by` Amazon | `inferred` |

Palantir does this as functions + models **on object types**, not as SPARQL over a blob of triples. An agent asks “who should we warn?” and gets `recommended_action = notify_buyer:Person:bob` because a **typed rule** walked `destined_for`, not because someone queried `MATCH (a)-[]-(b)`.

## What we refuse to be

- Neo4j + a chatbot
- GraphRAG over markdown
- OWL reasoner theater with no actions
- Generic `neighbors()` with no link names

If the only API is “put node / put edge / find path,” it is a KG. Quinovo’s API is: **load typed objects, run inference, act through named verbs, park anything under 80% for a human.**

## How a conclusion is allowed to exist

1. Premises are objects, **named** links, asserted facts, or forecasts.
2. A pack rule fires (`forecast_fact`, `fact_link_fact`, `prefix_link`).
3. The conclusion is an **inferred fact** (or inferred link) with `rule`, `confidence`, `provenance`.
4. Confidence **< 80%** → `pending` (HITL). **≥ 80%** → `asserted` (automated).
5. Agents may auto-act only on asserted facts / actionable forecasts.
6. Observed properties (`status: in_transit`) stay separate from inferred (`at_risk: true`). Mixing those is how KGs lie.

## The package story

Amazon’s file never said “at risk.” Inference says:

1. Forecast writes `late_risk` on Package `1Z999`.
2. Rule `at_risk_if_late`: if `late_risk ≥ 0.25`, infer `at_risk=true` (confidence = the forecast’s).
3. Rule `recommend_notify_buyer`: if `at_risk` **and** typed link `buyer` exists, infer `recommended_action=notify_buyer:Person:bob`.
4. A Hermes/ADK agent may then `apply_action` only if that fact is asserted — it does not invent Bob.

## Layers

Graph store is **under** inference. Inference sits on L3+L4+L8 and **feeds** L5 (actions) and L9 (agent tools: `run_inference`, `list_inferred_facts`). Type proposal/classification (L1) is a different AI path, same 80% HITL bar.
