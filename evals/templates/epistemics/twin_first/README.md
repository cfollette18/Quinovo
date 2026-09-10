# Twin first

Query the twin before answering it. Claims about live Quinovo state — objects, links, inferred facts, the review queue — must come from `get_object`, `search_around`, `filter_objects`, `list_inferred_facts`, `explain_fact`, `graph`, or a sibling read.

Coding work is out of scope. \"The twin does not know\" after an empty read is a pass. Recalling an object id from a previous session as if it were current is a fail.

| | |
|---|---|
| Score | boolean (`true` = grounded or no twin claim) |
| Attach to | the whole agent run (sample ~20%) |
| Variables | `{{user_input}}`, `{{output}}`, `{{tool_calls}}` |
