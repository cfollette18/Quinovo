# Hermes profile: `quinovo`

The user-facing Hermes agent for Quinovo. Hermes is the brain; Quinovo is the
world. This profile serves users by answering from the twin — typed objects,
named links, facts with provenance, forecasts with uncertainty — and acts only
through the pack's governed actions.

## Contents

| Path | Installs to | Purpose |
|---|---|---|
| `profile.yaml` | `~/.hermes/profiles/quinovo/` | Profile description (Hermes schema) |
| `SOUL.md` | `~/.hermes/profiles/quinovo/` | Persona: operator of the ontology |
| `AGENTS.md` | `~/.hermes/profiles/quinovo/` | Behavioral contract (reads, actions-only writes, review queue, no ticking) |
| `config.yaml` | `~/.hermes/profiles/quinovo/` | Model, approvals, `quinovo` MCP server block |
| `distribution.yaml` | `~/.hermes/profiles/quinovo/` | Distribution metadata (Hermes schema) |
| `skills.lock` | `~/.hermes/profiles/quinovo/` | Skill allowlist |
| `skills/using-quinovo/SKILL.md` | `~/.hermes/skills/mcp/using-quinovo/` | How to work the twin — no `tick` ritual, `save_turn` every turn |
| `rules/01-quinovo-is-the-world.mdc` | `~/.hermes/rules/` | Global rule: MCP tools only, `apply_action` only, review queue is the human's |

## Install

```bash
./scripts/install_hermes_profile.sh            # install / update (idempotent)
./scripts/install_hermes_profile.sh --uninstall
```

The script copies the files above into `~/.hermes/`, verifies that the MCP
server config exists at `~/.hermes/mcp/servers/quinovo.md` (warns, never
overwrites), and prints next steps. Profile runtime state (sessions, state.db)
lives in `~/.hermes/profiles/quinovo/` and is never touched by install or
uninstall.

Prerequisite: the `quinovo` MCP server registered with Hermes (stdio
`quinovo mcp --pack <pack> --db <db>`). The script only checks for it.

## No polling, no manual ticking

The profile's core behavioral rule. Quinovo's loop is event-driven: inference
fires when new information arrives — a source pull, an inbound hook, a series
point, an object write — and the twin the agent reads is already current. So
the agent:

- never calls `tick` or `run_inference` on a schedule, in a loop, or "first
  thing every session";
- reads the twin as it stands and trusts it;
- treats `tick` as a debug-only manual fallback for pack development.

The bundled skill and rule both state this; `AGENTS.md` makes it contractual.

## Event-driven wake-up (hook wiring)

The other half of "no polling": instead of the agent asking the world whether
anything changed, the world tells the agent. A Quinovo **outbound hook** fires
on bus events and POSTs to Hermes, so the `quinovo` agent wakes when the
review queue grows or a high-salience fact is asserted.

### Quinovo side (pack `hooks.yaml`)

```yaml
hooks:
  - name: hermes-review-queue
    on: fact.pending
    post: ${HERMES_HOOK_URL}        # see TODO below
    # Review queue needs a human — wake the agent to surface it.
  - name: hermes-high-salience
    on: fact.asserted
    where: {predicate: at_risk}     # optional: only high-salience predicates
    post: ${HERMES_HOOK_URL}
```

Outbound hooks fire from Quinovo's event bus; deliveries are audited, and
review-queue rules still apply to anything a hook-triggered agent does.

### Hermes side — TODO

> **TODO (Phase 7 / Hermes): the exact inbound endpoint is not yet pinned
> down.** What exists today in `~/.hermes/`:
>
> - **Shell hooks** (`~/.hermes/agent-hooks/*.sh`, wired under `hooks:` in
>   `config.yaml`) are *intra-session* hooks (`pre_llm_call`, `pre_tool_call`,
>   `post_tool_call`) — subprocess scripts with a JSON stdin/stdout protocol.
>   They cannot receive an external HTTP POST.
> - **Gateway hooks** (`~/.hermes/hooks/<name>/HOOK.yaml` + `handler.py`) run
>   inside the gateway process on Hermes lifecycle events (`gateway:startup`,
>   `agent:*`, `message:incoming`, ...). `message:incoming` is the natural
>   seam: a gateway hook could turn an externally delivered message into an
>   agent wake-up, but it is not itself an HTTP listener.
> - The gateway's `api_server` platform (`display.platforms.api_server`) is
>   enabled in this deployment and is the most likely receiving endpoint.
>
> Until Phase 7 lands the hook mechanism and the Hermes gateway endpoint is
> confirmed, point `post:` at a thin local receiver that injects the event as
> a message to the `quinovo` profile's gateway session, then replace it with
> the real endpoint. Suggested payload the receiver should preserve:
> `{name, created_at, actor, object_ref, detail}` (Quinovo's canonical event
> shape), so the agent wakes with enough context to call `explain_fact` or
> list the review queue without a round trip.

## Related

- MCP server config (prerequisite): `~/.hermes/mcp/servers/quinovo.md`
- Dashboard plugin: `integrations/hermes-dashboard/`
- Vocabulary used throughout this profile: `docs/conventions.md`
