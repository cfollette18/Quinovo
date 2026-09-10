# Named action

`apply_action` (or `propose_action`, which parks below 0.8) is the write when the pack already has a verb. `upsert_object` / `set_link` / `delete_object` are capture paths for sources and `save_turn`, not a way around `mark_todo_shipped` or `archive_topic`.

| | |
|---|---|
| Score | boolean (`true` = named action or capture-only) |
| Attach to | the whole agent run |
| Variables | `{{user_input}}`, `{{output}}`, `{{tool_calls}}` |
