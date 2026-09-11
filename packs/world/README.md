# world pack

The `world` pack is the agent's own memory as a typed, queryable ontology.
Any MCP agent (Cursor, Hermes, Claude) captures what happened, and the loop
turns it into entities, triples, and open work it can answer questions from
next session.

## The model

Three layers, all typed:

```
Topic ──────────< in_topic ──── Conversation, Fact, Memory, Todo,
  │                             Decision, OpenQuestion, Skill, Project
  └── subtopics                 (and Entity, through entity_in_topic)

Entity ◄── fact_subject ─── Fact ─── fact_object ──► Entity
  ▲                          (subject, predicate, value, confidence)
  └── mentions ── Conversation
  └── about ───── Todo, Decision, OpenQuestion, Memory
```

- **Topic** is a basket: `quinovo`, `cretex`, `cretex/workflows`. Baskets nest.
- **Entity** is a noun the world keeps talking about: a person, organization,
  system, tool, project, place, or concept. One row per thing, slug id,
  aliases for the other spellings.
- **Fact** is a triple: `subject predicate value`. When the subject or the
  value is an Entity the Fact is linked to it, so `about("Langfuse")` walks
  every claim in both directions.
- **Conversation** is one turn. It links to the Entities it mentions and to
  every Fact, Decision, Todo, OpenQuestion, Memory, and Skill it produced.
- **Memory / Decision / Todo / OpenQuestion / Skill** are the durable
  artifacts of a turn. Each is filed in a Topic and, when it concerns an
  Entity, linked `about` it.

## How knowledge gets in

1. An agent calls `save_turn` with structured items, or `remember` with raw
   text, at the end of a turn. Missing Topics are created.
2. `tick` (the background loop) pulls Cursor transcripts as Conversations, so
   a forgotten capture still lands.
3. For every Conversation it has not seen, the loop asks the configured
   language model for entities and triples, resolves them against existing
   Entities (id, name, alias), and writes linked Facts. Without a model it
   only links mentions of Entities it already knows. It never invents a
   Person from a capitalized word.
4. Typed inference flags stale work (`todo_stale`, `question_stale`) and
   memories old enough to re-confirm (`memory_aging`).

## How agents read it

- `briefing()` at session start: active topics, open and stale todos, open
  questions, recent decisions, what is waiting on a human.
- `about(name)` before answering about something: the Entity or Topic, its
  facts as sentences, related entities, and the open work that concerns it.
- `recall(query)` for anything else: text search across every type, ranked,
  bounded.
- `get_object`, `search_around`, `filter_objects` for exact walks.

## Actions

| Action | What it does | Unattended? |
|--------|--------------|-------------|
| mark_todo_captured | sets `Todo.status = captured` | yes |
| mark_todo_shipped | sets `Todo.status = shipped` | yes |
| mark_question_answered | sets `OpenQuestion.status = answered` | yes |
| archive_topic | sets `Topic.status = archived` | no, explicit call only |

## Inference rules

`inference.yaml` is deliberately small. A rule earns its place only when
the fact it produces changes what a human or an agent does next. Rules
that restate a property (`status=open` therefore `open`) are noise.

## Seed

`seed.yaml` creates the Topics we already know we care about (quinovo,
cretex and its subtopics, jig, orzo) and the user as a Person. Re-running
it is idempotent.
