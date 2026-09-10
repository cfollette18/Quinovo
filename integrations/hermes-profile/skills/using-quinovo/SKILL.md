---
name: using-quinovo
description: Use the Quinovo MCP server as the operational ontology. Read the twin, act through apply_action, save_turn every turn.
---

# Using Quinovo

Quinovo is already connected as the `quinovo` MCP server. Call its tools. Do not open SQLite. Do not PATCH. Do not write a second client.

Hermes is the brain. Quinovo is the world. The loaded pack is `world`.

## Every session

There is no session-start ritual. The loop is event-driven — inference runs when new information arrives (source pulls, inbound hooks, series points, object writes), never because an agent asked.

1. Do the work — query the twin with the read tools.
2. Call `remember` at the end of **every** turn with the raw turn text (plus topic when you know it) — it extracts entities and relations and writes linked Facts, Memories, and Persons in one call. Use `save_turn` only when you already have structured facts, decisions, todos, questions, memories, and skills. Never skip the end-of-turn capture. Missing topics are created.

Cretex work files under `cretex`, with subtopics `technology` (Ivanti, Epicor, Jira) and `workflows` (ticket-automation, epicor-user-termination, documentation-automation, faq-bot — planned automations, not MCP servers). Use `topic: "cretex/workflows"` (or `parent: cretex`) plus `project` when grouping a named initiative.

## Tools

Read: `list_object_types`, `get_object`, `search_around`, `filter_objects`, `get_series`, `list_inferred_facts`, `explain_fact`, `graph`

Capture: `remember` (raw text in, linked knowledge out), `save_turn` (already-structured items)

Act: `list_actions`, `apply_action` — the only legal typed edits besides `save_turn` / `upsert_object` / `set_link`

Review queue: `list_inferred_facts` (status `pending`), `list_proposals`, `list_pending_actions` — surface these to the human; never approve unprompted.

Debug only: `tick`, `run_inference` — manual fallback for pack development and debugging. Never scheduled, never "first thing", never to make the twin fresh. The twin is already fresh.

Pending inferred facts are below the pack's auto-apply confidence threshold and wait for a human. Unattended vs approval is a per-action flag.

## How to work

1. `search_around` on the active Topic — walk named links, never SQL.
2. Answer observed vs inferred: properties are observed, facts carry a rule and confidence, forecasts carry an uncertainty band. Offer `explain_fact` for any fact you cite.
3. `remember` before you stop talking.
