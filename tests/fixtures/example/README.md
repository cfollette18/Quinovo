# Example pack — one teaching world

This pack is **not** Quinovo. It is a starter ontology so you can see inference and actions before you rename the nouns. Copy it (`quinovo init`), swap the types, keep the engine.

The story: Bob bought lipstick. Amazon shipped it.

Package `1Z999` **contains** Product `lipstick-1`, is **destined_for** Person `bob`, is **shipped_by** Company `amazon`.

That graph is the dump. `inference.yaml` is the rest: late forecast → `at_risk` → `notify_buyer` for Bob; tracking ids starting `1Z` infer Amazon. Below 80% confidence those facts stay pending.

MCP `apply_action(notify_buyer)` warns Bob only if the recommendation is asserted. `mark_delivered` is the only write of observed status. A second package in this pack (`UPS001`) exists so security can show row-level denial — still example data, still not the product.
