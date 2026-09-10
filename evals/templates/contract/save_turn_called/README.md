# save_turn called

Fluency is not memory. A complete answer that never called `save_turn` left nothing in the world pack.

This judge looks at **tool calls**. True means Quinovo `save_turn` ran with a non-empty `topic` and `summary`. Tick pulling transcripts is a fallback, not a substitute.

| | |
|---|---|
| Score | boolean (`true` = called) |
| Attach to | the whole agent run |
| Variables | `{{user_input}}`, `{{output}}`, `{{tool_calls}}` |
