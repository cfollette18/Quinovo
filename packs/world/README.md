# world pack

The `world` pack is the conversational knowledge ontology. It is the
recommended pack for the Hermes agent (or any agent) that wants to
**autonomously capture every conversation, every decision, every
memory, every todo, and every skill into a typed, queryable world.**

The other packs in this repository (`example`, `clinic`, `homelab`) are
domain-specific tutorials. This one is the agent's own memory.

## The topic model

The top-level concept is a **Topic**. A Topic is a named subject area
the agent works in: `quinovo`, `cretex`, `jig`, `orzo`, or a project of
yours. Topics can have subtopics (`cretex` has `ivanti`, `epicor`,
`jira`).

Everything else hangs off a Topic through the `belongs_to` link:

```
Topic ──< belongs_to ──  Conversation
                        Fact
                        Memory
                        Todo
                        Decision
                        OpenQuestion
                        Skill
                        Project
```

If a Fact is asserted about a Topic that doesn't exist yet, Quinovo's
typed inference layer proposes creating the Topic (HITL below 80%
confidence). The world grows without a human in the loop, but the
human stays in the loop for anything uncertain.

## The capture contract

The agent's job on every turn is to write structured objects, not
prose. The shape of one turn:

1. The agent reads the user's turn.
2. The agent extracts the structured claims: what facts were stated,
   what decisions were made, what questions are still open, what work
   is now open, what memories are durable.
3. The agent writes one `Conversation` object (one per turn) and
   links it to the active Topic through `belongs_to`.
4. The agent writes each structured claim as its own object
   (`Fact`, `Decision`, `OpenQuestion`, `Todo`, `Memory`, `Skill`)
   and links it back to the Conversation.
5. The kernel nudges itself so inference + unattended actions fire
   immediately, instead of waiting for the 2-second tick. Missing Topics
   are created. Nested topics use slashes (`cretex/workflows`).

Implementation note: the agent calls the `remember` MCP tool at the end
of every turn with the raw text (`save_turn` only when it already has
structured items). Every tick then enriches new Conversations with the
semantic connections a human would see — who did what to whom, what
contains what, what each thing is, what that implies — as linked Facts,
Memories, and Persons, so knowledge grows even when the agent never calls
`tick` itself. Tick also pulls the `transcripts` source so Cursor jsonl
chats land in the world even when an agent forgets capture entirely.

## Why this pack exists

Without a typed world, an agent's "memory" is either a transcript
dump or a free-form list of strings. Both fail at scale:

  - Transcripts are unstructured. You cannot ask "what did we decide
    about Ivanti last month?" without a vector search that hallucinates.
  - String memories decay. Two memories say the same thing slightly
    differently and neither dedups.

The `world` pack is a third option: a small set of types, a small set
of links, and a typed inference layer that promotes structured
observations into typed knowledge. The agent doesn't have to remember
to write to a memory file; it just writes the world and the world
remembers.

## Object reference

| Type | Purpose | Cardinality |
|------|---------|-------------|
| Topic | Top-level subject area | one per domain |
| Conversation | One per turn | one per turn |
| Fact | One per claim | many per conversation |
| Memory | Cross-session durable fact | curated by the agent |
| Decision | A choice that was made | rare, important |
| OpenQuestion | A question still open | surfaced at session start |
| Todo | A unit of open work | created by turns, shipped by turns |
| Skill | A saved procedure | mirrored from SKILL.md on disk |
| Project | A named initiative under a Topic | optional grouping |
| Person | A human | the user, plus anyone named |

## Link reference

| Link | From → To | Purpose |
|------|-----------|---------|
| belongs_to | (any) → Topic | the core hanging-off link |
| produced | Conversation → Fact | a turn yields facts |
| decided | Conversation → Decision | a turn lands a decision |
| raised | Conversation → OpenQuestion | a turn raises a question |
| spawned | Conversation → Todo | a turn spawns work |
| recorded | Conversation → Memory | a turn yields a memory |
| authored | Conversation → Skill | a turn yields a skill |
| under_project | (any) → Project | group by initiative |
| owns | Person → Memory / Todo | the human owns it |
| authored | Person → Decision | the human made the call |
| subtopic_of | Topic → Topic | sub-topics for scope |

## Action reference

| Action | What it does | Unattended? |
|--------|--------------|-------------|
| mark_todo_captured | sets `Todo.status = captured` | yes |
| mark_todo_shipped | sets `Todo.status = shipped` | yes |
| mark_question_answered | sets `OpenQuestion.status = answered` | yes |
| archive_topic | sets `Topic.status = archived` | no — explicit call only |

## Inference rules

`inference.yaml` is intentionally conservative. We do not invent facts
from absence. The rules:

  - `mark_conversation_captured` — any Conversation with `recorded_at`
    and `session_id` is auto-marked as `captured`.
  - `todo_has_topic` — an open Todo is `scoped` if it has a Topic.
  - `decision_is_canonical` — a Decision with confidence ≥ 0.9 is
    `canonical`.
  - `link_memory_to_matching_topic` — a Memory whose `id` starts with
    a known Topic slug is auto-linked to that Topic (HITL below 80%).

## Bootstrapping a fresh world

```bash
# 1. Wipe any old data
rm -f /home/cfollette18/projects/Quinovo/.data/quinovo.sqlite

# 2. Start the kernel pointing at this pack
quinovo serve \
  --pack /home/cfollette18/projects/Quinovo/packs/world \
  --db /home/cfollette18/projects/Quinovo/.data/quinovo.sqlite

# 3. Load the seed (Topics + Person)
# The kernel exposes /v1/funnel/seed as a POST. From the CLI:
quinovo tick  # one autonomous pass — also re-runs the seed loader
```

## Using the dashboard

```bash
hermes dashboard   # opens http://127.0.0.1:9119
```

Click the **Quinovo** tab. The default panel shows the typed graph
for whatever Topic you query. Use the search bar to filter by
object type.

If `quinovo serve` is on a non-default port, set `QUINOVO_URL` before
launching the dashboard.
