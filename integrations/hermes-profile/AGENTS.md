# Quinovo — agent map

This file is a map, not a manual. If a behavior is not reachable from here, it
does not exist to the agent.

## What you are connected to

The `quinovo` MCP server is the world. It exposes the loaded pack as tools.
You do not open the SQLite file, run SQL, `PATCH` the HTTP API, or write a
second client. MCP tools are the whole interface.

## Reads — always by tool

| Need | Tool |
|---|---|
| What types exist in the pack | `list_object_types` |
| One object, with its facts and forecasts | `get_object` |
| Walk a named link side | `search_around` |
| Objects of a type, by property | `filter_objects` |
| A metric's series window | `get_series` |
| Inferred facts (optionally by status) | `list_inferred_facts` |
| Why a fact was concluded | `explain_fact` |
| The whole graph | `graph` |
| The pack's YAML | `read_pack` |
| Sources, logic sources, action targets | `list_sources`, `list_logic_sources`, `list_action_targets` |

## Writes — actions only

`apply_action` is the only legal write to the world. Check `list_actions` for
what the pack governs. Unattended actions apply immediately; approval-gated
actions queue and appear in the review queue — that is the pack working as
designed, not an error to route around.

Never `upsert_object`, `set_link`, `delete_object`, or `append_series` as a
shortcut for an action the pack already defines. Those tools exist for capture
paths (sources, `save_turn`); when a governed action covers the change, the
action is the write.

## The review queue belongs to the human

The review queue is pending facts (`list_inferred_facts status=pending`),
pending proposals (`list_proposals`), and pending actions
(`list_pending_actions`). Your job is to **surface** it: when it is non-empty
and relevant, tell the human what is waiting, with confidence and provenance.
The human approves or rejects — normally in the workspace (**Inference** tab),
or by explicitly directing you to call `approve_inferred_fact`,
`approve_proposal`, `approve_pending_action` / their reject counterparts. Low
confidence stays pending until a human moves it. You never approve unprompted.

## The loop runs itself — no ticking

Quinovo's loop is event-driven: inference fires when new information arrives
(a source pull, an inbound hook, a series point, an object write), not on a
schedule and not because an agent asked. Therefore:

- **Never call `tick` on a schedule, in a loop, or "first thing every
  session."** There is no session-start ritual.
- **Never call `run_inference` to "refresh" before answering.** Read the twin
  as it stands; the facts and forecasts you see are current.
- `tick` and `run_inference` remain only as **manual debug tools** — e.g. the
  user is developing a pack and wants to watch a pass fire. Say that is what
  you are doing when you do it.

## Answering discipline

1. Query first, answer second. If the twin can tell you, ask the twin.
2. Separate observed from inferred: properties are observed; facts are
   machine-made conclusions with a rule and a confidence; forecasts are
   predicted metric values with a horizon and an uncertainty band. Report
   which kind a number is.
3. Provenance on offer: for any fact you cite, be ready with `explain_fact`.
4. If the twin does not know, say the twin does not know. Do not fill the gap.

## Capture

Call `save_turn` at the end of **every** turn — topic, summary, and every
fact, decision, todo, question, memory, and skill from the turn. Never skip
it; missing topics are created. This is how the world remembers the
conversation.
