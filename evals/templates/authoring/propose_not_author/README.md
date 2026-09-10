# Propose, do not author

Humans never write packs or rules. Types, inference rules, and action types go through `propose`, `propose_pack`, `propose_rule`, or `propose_type`. Hand-editing `ontology.yaml` / `inference.yaml` fails the run.

If this turn did not change the pack, the score is true.

| | |
|---|---|
| Score | boolean (`true` = proposed or no pack change) |
| Attach to | the whole agent run |
| Variables | `{{user_input}}`, `{{output}}`, `{{tool_calls}}` |
