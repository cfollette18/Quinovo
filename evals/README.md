# evals

Quinovo-specific LLM judges, kept here so they are not mixed with the generic
agent-eval-templates catalog.

Source of truth: https://github.com/cfollette18/quinovo-eval-templates

Langfuse install names them `quinovo/<id>` (a **quinovo** folder in the UI) and
attaches live rules to observations tagged `quinovo`. Agent-run judges score
Cursor turns. The inference judge scores `pending_hitl` observations — one
parked proposal, inferred fact, or pending action each. Agent-run failures
land in `quinovo/eval-failures`; experiments on that dataset retrigger the
same judges.

```bash
./evals/install.sh
./evals/install.sh --ids hitl_worthy --rule
```

That loads `Quinovo/.env` (Langfuse keys already there) and posts judges,
live rules, the eval-failure dataset, and the experiment rule to
http://localhost:3000. Cursor turns that call Quinovo MCP are tagged
`quinovo` by `~/docs/langfuse/scripts/cursor_hook.py`. Kernel parks emit a
`pending_hitl` span tagged `quinovo` + `hitl`.
