# Structured capture

Transcripts are not facts. A turn that decided something, opened work, or stated a claim must write those as objects.

This judge labels the **run**: `complete`, `partial`, `skipped`, `none_needed`, or `unknown`. Facts use `predicate`, `value`, and `confidence` — not a prose blob on the Conversation summary.

| | |
|---|---|
| Score | categorical |
| Attach to | the whole agent run |
| Variables | `{{user_input}}`, `{{output}}`, `{{tool_calls}}` |
