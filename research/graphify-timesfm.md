# Graphify and TimesFM

Neither tool is an ontology. Both are useful **inside** Quinovo if they stay in the right layer.

## Graphify

[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) turns a folder (code, systemd units, markdown, PDFs, images) into a local knowledge graph: `graph.json`, wiki, MCP, EXTRACTED / INFERRED / AMBIGUOUS edges. NetworkX + tree-sitter + an LLM. No live object store, no actions, no ACLs.

**Sits in**

- **L1:** proposed object/link types from repos and runbooks (suggestions, not OMS)
- **L10:** agent-navigable wiki of the compiled schema + pack docs

**Does not sit in** L3. Do not dump 15-second telemetry into markdown and graphify it. Do not store live Device instances in `graph.json`. That graph goes stale when the indexer host sleeps.

Quinovo should compile L1 + pack markdown into a wiki and optionally run Graphify `--mcp` against that corpus so an agent can answer “what connects `qwen35-server` to mem0” without reading the whole repo.

## TimesFM

[google-research/timesfm](https://github.com/google-research/timesfm) is Google Research’s time-series foundation model (forecast point + quantiles). TimesFM 2.5 weights are Apache-2.0. **TimesFM 3.0 pretrained weights are non-commercial / non-production** (`timesfm-non-commercial-license-v1.0`).

**Sits in L8** as one Model implementation.

Typical binding (Palantir’s “predictive ontology” is this, not a second graph):

1. Funnel or a collector writes `Device.cpu_pct` as a time-series property (L4).
2. A function reads a window of that series.
3. TimesFM 2.5 returns horizon + quantiles.
4. Funnel or the function writes `Device.cpu_pct_p90_4h` (and `forecast_model`, `forecast_as_of`, `skill_mae`) on the **same** Device, or creates a linked `Forecast` object.
5. An action type may trigger `run_forecast_now`. Alerts fire from rules on actuals **and** forecast quantiles.

TimesFM is not causal. It will not say why heater OOMs. Pair forecasts with Graphify/`depends_on` links for explanation. Gate production alerts on backtest MAE. Do not fine-tune on two days of data.

**Hardware:** do not run TimesFM beside llama-server on an 8GB Orin. Forecast jobs belong on the always-on stem (planned: pi5) or a laptop, not on `heater`.

## Mapping sentence

> Graphify teaches agents the **language**. TimesFM writes **numbers onto objects**. Quinovo is the object API those two plug into.
