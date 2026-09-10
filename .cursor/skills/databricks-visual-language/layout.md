# Layout (Databricks.com → Quinovo)

Reference: homepage and product pages on databricks.com. Palette stays Lava / Navy / Oat.

## Page shell

- Sticky header, ~64–72px, oat/white with hairline `--border`. Wordmark left, links, **one** Lava CTA right. CTA stays visible when the menu collapses.
- Content max-width **1280px**, horizontal padding 32 / 24 / 16 (desktop / tablet / mobile).
- Section vertical padding: hero **96–120px**, major bands **96px**, minor **64px**. Tight 56px padding reads cheap next to Databricks.
- Footer is a **navy** full-bleed band. Do not put a second navy band immediately above it.

## Dual-mode by section

No site-wide dark theme toggle. Alternate:

```
[oat/white] hero
[oat/white] proof or product-card grid
[navy / navy-900] ONE product showcase + large diagram
[white] features / FAQ
[navy] footer
```

Never two consecutive dark bands. Navy `#1b3139` is both **ink** and **product-stage background**.

## Hero (non-negotiable)

Two columns on desktop, stack on `<1024px` (graphic below type).

```
+------------------+---------------------------+
| kicker           |                           |
| H1 (max ~16ch)   |   LARGE GRAPHIC / DIAGRAM |
| lede (~40–56ch)  |   (min ~480px wide)       |
| [Lava CTA] [Ghost]|                           |
| proof row        |                           |
+------------------+---------------------------+
```

- Type column ~560–720px. Headline `clamp(40px, 5vw, 64px)`, weight 500, tracking `-0.03em`.
- Pair CTAs: Lava primary + navy ghost. Secondary may be “See how it works” / play, not a second Lava button.
- The right visual is the characteristic object: animated loop diagram, workspace mockup, or exploded four-primitive stack. A radial gradient behind copy is **not** a graphic.

## Section anatomy

Every major section:

1. Small kicker (Lava, 12–14px, sentence case — not tracked ALL CAPS).
2. H2 ~32–48px, weight 500, max ~20ch.
3. Optional lede, muted, ~680px.
4. **The visual or a 2–3 column card grid with graphics**, then supporting copy.

Left-aligned type. Do not center-stack a landing the way a startup template does.

## Grids

| Pattern | Use |
|---|---|
| Split 1fr / 1fr | Hero, how-it-works (copy + diagram) |
| 3-up | Product / why cards with illustration headers |
| 4-up | Four primitives — each cell has a mini diagram, not a label only |
| Logo/proof strip | Unified-height marks, no card chrome |
| FAQ accordion | After the visual story, max ~720px |

Product cards: illustration **top 40–50%** of the card, then title + one sentence. Equal text-only tiles are the current Quinovo miss.

## How-it-works / platform band

This is the Databricks “Build and run…” block:

- Full-bleed **navy** stage.
- Optional pill tabs (20px radius **only here**) to switch diagram states.
- Left: title + short capability copy for the active tab.
- Right / below: the **diagram fills the band** (see graphics.md).

Do not explain the loop as a horizontal `span.loop-node` rail. That is a legend, not a layout.

## Workspace chrome (app, not marketing)

Keep rail + topbar + body. Match Databricks **density and quietness**, not the marketing hero:

- Oat rail, white topbar, oat canvas.
- Active nav: inset Lava bar, not a colorful icon.
- Empty states: one sentence + one ghost CTA. Optional small geometric SVG, not a marketing diagram.

## Responsive

- `<640px`: single column; hero graphic under type; 3-up → 1.
- `640–1024`: 2-up cards; hero may keep split if the graphic can shrink to ~320px.
- `>1280`: 1280px cap, extra margin is empty oat — do not stretch type to the viewport edge.
