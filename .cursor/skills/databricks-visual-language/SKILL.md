---
name: databricks-visual-language
description: Match Databricks.com layout, motion, and especially graphics/diagrams on the Quinovo site while keeping the Lava/Navy/Oat palette. Use when editing landing, chrome, CSS, SVG, heroes, how-it-works, architecture diagrams, product visuals, or any file under src/quinovo/apps/.
---

# Databricks visual language (Quinovo)

Quinovo's **colors stay**. Match [databricks.com](https://www.databricks.com/) on **layout, animation, and graphics** — diagrams first.

Locked palette (CSS vars only, never new brand hues):

| Token | Hex | Role |
|---|---|---|
| `--lava` | `#ff3621` | Primary CTA, one hot mark in a diagram |
| `--lava-pressed` | `#eb1600` | Pressed CTA |
| `--navy` | `#1b3139` | Ink + dark product bands |
| `--navy-900` | `#0b2026` | Deepest dark sections |
| `--oat` / `--oat-mid` | `#f9f7f4` / `#eeede9` | Warm canvas |
| `--white` | `#ffffff` | Cards, light bands |
| `--muted` | `#5f737d` | Secondary copy |

Read before building:

- Layout → [layout.md](layout.md)
- Graphics and diagrams (priority) → [graphics.md](graphics.md)
- Motion → [motion.md](motion.md)

## What "match Databricks" means here

Not a clone of Databricks copy or product. Steal the **spatial and graphic system**:

1. Every major claim has a **large visual** (diagram, mockup, or animated geometry) — never a text-only hero or a `Data → Propose → Approve` label rail as the explanation.
2. Page rhythm **alternates** light oat/white bands with **one** full-bleed navy product band. Dual-mode is by section, not a theme toggle.
3. Graphics are **geometric architecture**: square nodes, layer stacks, pipeline flows. The Quinovo mark (diamond ring, four squares, Q-tail) is the primitive — like Databricks bricks.
4. Motion is **quiet infrastructure**: 150/240/320ms, no bounce, pause control on looping decoration, `prefers-reduced-motion` honored.

Human-first copy and no raw JSON still apply (`.cursor/rules/no-json-blocks.mdc`).

## Current Quinovo gaps (fix these, don't preserve them)

Landing today is Databricks **palette** with a **generic SaaS text page**. When touching `landing.py` / `landing.css`:

| Now | Databricks-matched |
|---|---|
| Hero is copy + two buttons only | Split hero: type left (~56ch), **large graphic right** |
| Loop is a dashed text rail of nodes | Full-width **animated architecture diagram** |
| Why cards are iconless text tiles | Product cards with a **graphic occupying the top third** |
| Almost no motion | Scroll reveal once per section; diagram idle animation |
| `--maxw: 1080px` | Content cap **1280px**, hero padding **96–120px** |

Workspace graph (`dashboard.html`) may stay an operational map. Marketing and empty states must not look like that map shrunk into a card.

## Build order

1. Draw the graphic or diagram first (SVG in the Python template or a dedicated helper). If the visual cannot explain the section without the headline, it is too weak.
2. Place it in the Databricks layout slot (hero right, dark-band stage, or card header).
3. Add motion last, using tokens in [motion.md](motion.md).
4. Grep: no `json-panel`, no `<pre`, no new palette hexes outside CSS vars.

## Do not

- Recolor the brand. No purple AI gradients, no cyan "data" chrome, no cream/terracotta AI-default skins.
- Put accent hues on buttons, nav, or type. Extra hues (existing `--blue`, `--green`, `--yellow`, `--maroon` in `chrome.css`) are **diagram-only**, same as Databricks cyan/violet inside illustrations.
- Ship stock undraw/humaaans, 3D clay blobs, or generic Lucide-in-a-circle as the hero.
- Animate every card on scroll. One orchestrated entrance per section; stagger children 80ms.
- Change DM Sans / DM Mono or the 2px CTA radius already in Quinovo CSS.
