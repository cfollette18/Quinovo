# Agent-run dataset

A Langfuse dataset of Quinovo agent runs that failed a catalog judge.

Live rules already score observations tagged `quinovo`. This template turns those
failures into dataset items, then attaches the same judges to experiments on
that dataset so a rerun is scored automatically.

| | |
|---|---|
| Dataset | `quinovo/eval-failures` |
| Input | `user_input`, `output`, `tool_calls` — the fields every judge already reads |
| Expected | the passing contract (save_turn ran, no MCP bypass, HITL left to the human, …) |
| Trigger | a catalog score in the fail bucket |

`mcp_bypass` fails when the score is **true**. Every other boolean fails when **false**. `structured_capture` fails on `partial` or `skipped`.
