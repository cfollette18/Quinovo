---
name: frontend-design
description: Quinovo frontend design language — human-first, no JSON blocks, Databricks-styled (Lava/Navy/Oat/DM Sans), agent logo cards for MCP clients. Use when editing any file under src/quinovo/apps/ or rendering HTML to the user.
---

# Quinovo frontend design language

The Quinovo frontend is **human-first**. Humans are approvers, not builders;
the loop runs itself. Every page must read like plain language a non-technical
approver can act on. Raw JSON is never shown. This skill codifies the design
language an agent must follow when touching anything under
`src/quinovo/apps/`.

## Hard rules

1. **Never render raw JSON.** No `<details class="json-panel">`, no
   `<pre>` JSON/YAML dumps, no `JSON.stringify(...)` on the page. The
   `quinovo/apps/chrome.py::json_panel` helper is a no-op (`return ""`); do
   not call it and do not reintroduce it. See
   `.cursor/rules/no-json-blocks.mdc`.
2. **Show human language.** Use `quinovo/apps/humanize.py` to turn kernel
   data into sentences: `title_case`, `fact_line`, `status_label`,
   `confidence_label`, `object_name`, `kind_label`, `actor_label`. Never
   show `predicate=value` or `Type:id` — always a sentence.
3. **Power users get the API, not a JSON block.** Link to the JSON endpoint
   (e.g. `/contract.json`) or use a **Copy config** button that fetches the
   config as plain text and puts it on the clipboard. The raw config is
   never rendered on the page.
4. **Agent connection = logo cards.** Use `quinovo/apps/agents.py`:
   `AGENTS`, `logo_svg`, `launch_command`. Each agent is a card with an
   inline-SVG logo, name, one-line blurb. Expanding reveals plain-language
   steps + a **single-line** launch command in a styled `<input>`
   (`.agent-cmd`), plus a **Copy config** button. JSON-behind-a-button is
   **not** allowed — the button fetches from `/connect/config/{agent}` and
   copies; it does not reveal a `<pre>`.

## Visual language — Databricks layout, Quinovo palette

Palette is **locked**: Lava / Navy / Oat CSS vars. Do not introduce new brand
hues. Match databricks.com on **layout, motion, and especially diagrams**.
Full spec: `.cursor/skills/databricks-visual-language/SKILL.md`.

- **Type**: DM Sans for text, DM Mono for code/paths.
- **CTAs**: square corners (`border-radius: 2px`), solid Lava primary,
  Navy-ghost secondary. `.btn`, `.btn-primary`, `.btn-ghost` already exist.
- **Hero / how-it-works**: split layout + large inline SVG diagram, never a
  text-only rail (`Data → Propose → Approve`).
- **Logos**: inline SVG only. No hotlinked images. Agent logos live in
  `apps/agents.py::_LOGOS`.

## Layout primitives

- **Workspace chrome** (`apps/chrome.py::wrap`): left rail (icons) + topbar
  (wordmark, search, pack label, avatar) + body. Pages render inside this
  via `wrap(title, body, nav=..., pack_name=..., extra_script=...)`.
- **Landing page** (`apps/landing.py`): standalone, no workspace chrome.
  Hero → Why grid → How it works (primitives + loop) → Connect (agent
  cards) → footer.
- **Connect flow** (`apps/connect_view.py`): sign-in gate → guided page
  with `agent-meta` (pack/db paths) + agent logo cards + test-connection.

## Where things live

| Concern | File |
|---|---|
| Workspace chrome, nav, `wrap`, `esc` | `src/quinovo/apps/chrome.py` |
| Chrome CSS | `src/quinovo/apps/chrome.css` |
| Landing page + CSS | `src/quinovo/apps/landing.py`, `landing.css` |
| Sign-in + guided connect | `src/quinovo/apps/connect_view.py` |
| Agent logos + cards | `src/quinovo/apps/agents.py` |
| Human-language labels | `src/quinovo/apps/humanize.py` |
| Graph dashboard | `src/quinovo/apps/dashboard.html` |
| Object / Catalog / Inference / Audit / Settings / Train / Sources / SDK |
  `object_view.py`, `schema_manager.py`, `inference_view.py`,
  `audit_view.py`, `settings_view.py`, `train_view.py`, `sources_view.py`,
  `sdk_view.py` |

## Definition of done for any frontend change

- Grep the rendered page: no `json-panel`, no `jsonPanel`, no `<pre`,
  no `cfg-code`/`cfg-toggle`/`cfg-grid` JSON dumps.
- Any new page test asserts `"json-panel" not in page.text` and
  `"<pre" not in page.text`.
- No API keys, secrets, or key tails leak into rendered HTML.
- The page reads as sentences a non-technical approver can act on.

## Do not revert

Autonomous inference, the Settings rail, the Train tab, the Databricks
workspace chrome, MCP tools, ontology-vision work, and the connect sign-in
flow are all in scope for this design language — coordinate, don't clobber.
