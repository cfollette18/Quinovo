# evals

Quinovo-specific LLM judges, kept here so they are not mixed with the generic
agent-eval-templates catalog.

Source of truth: https://github.com/cfollette18/quinovo-eval-templates

Langfuse install names them `quinovo/<id>` (a **quinovo** folder in the UI) and
attaches live rules to observations tagged `quinovo`.

```bash
./evals/install.sh
```

That loads `Quinovo/.env` (Langfuse keys already there) and posts judges +
rules to http://localhost:3000. Cursor turns that call Quinovo MCP are tagged
`quinovo` by `~/docs/langfuse/scripts/cursor_hook.py`.
