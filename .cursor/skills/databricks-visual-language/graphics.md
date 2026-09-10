# Graphics and diagrams (priority)

This is the gap. Databricks looks like Databricks because **architecture is drawn**, not described. Quinovo must do the same with Lava / Navy / Oat and the knot-Q mark.

## Primitive: the Quinovo mark, exploded

From `chrome.py` / `landing.py` bricks SVG:

- Diamond ring, **miter** joins, square caps
- Four **10×10 squares** at the cardinals; **top square is Lava**, others Navy
- Q-tail as a square stroke

Every marketing diagram is this geometry at scale: square nodes, orthogonal or 45° connectors, one Lava focal. Not circles, not pills, not isometric clay, not photos of people.

## What Databricks diagrams actually look like

- Abstract **boxes**, **layer stacks**, **pipeline arrows**
- Navy structure, light oat/white stage, **one** hot path in Lava
- Extra hues only **inside** a diagram (Quinovo may use existing `--blue` `#2272b4`, `--green` `#00a972`, `--yellow` `#ffab00`, `--maroon` `#98102a` as series colors on the graph/diagram — never on chrome)
- No characters, no undraw, no 3D product-shot stock
- Recognizable as the brand **before** the wordmark

Treat charts the same: geometric, one finding, navy bars or one Lava series, no rainbow, no soft chart shadows.

## Required visuals (landing)

### 1. Hero graphic (must exist)

A single inline SVG (or SVG + CSS), **at least as tall as the type column**. Pick one system and commit:

**A. Cycle diagram (preferred for Quinovo)**  
Four square stations on a rounded-rect or diamond loop: Data → Propose → Approve → Act. A Lava square token travels the path (`offset-path` or SMIL). The active station fills Navy; idle stations are oat with navy stroke.

**B. Layer stack**  
Four platforms stacked (Security, Action, Logic, Data) as navy slabs on oat, isometric-ish **2.5D** (simple parallelograms, not a 3D engine). Lava tick on the layer the copy is about.

**C. Workspace mockup**  
Framed screenshot of the real graph UI in a 12–16px radius stage, navy window chrome, hairline border, teal-tinted shadow `0 24px 48px rgba(27,49,57,0.16)`. Not a raw `<svg id="svg">` dumped from the app.

Hero right column is **never** a CSS radial-gradient with no drawable object.

### 2. Dark-band architecture diagram

On the navy how-it-works section: a **wide** SVG (full content width). Show the kernel as a system:

```
  [sources / MCP] --pipe--> [Data] --pipe--> [Logic]
                                |               |
                                v               v
                            [Approve HITL]   [Action write-back]
```

Rules:

- Nodes = squares or 2px-radius rects, navy fill on oat **or** oat fill with 1.5px oat stroke on navy ground
- Edges = 1.5–2px strokes, `stroke-dasharray` + `stroke-dashoffset` animation for flow
- Labels in DM Sans, 12–14px, oat on navy
- One Lava node = the human approval gate
- `aria-hidden="true"` on decorative SVG; nearby H2/lede carry the meaning. If the diagram is the only explanation, add a `<title>` / visually hidden caption.

### 3. Card-header mini diagrams

Each why/product card gets a **120–160px** tall SVG header (not a 24px icon). Same stroke language. Three-up grid, graphic first.

### 4. Workspace / empty states

Small mark or 3–4 square nodes. Do not paste the marketing hero into the rail.

## SVG craft

- Inline SVG in the template (or a Python helper that returns SVG). No hotlinked images. No PNG heroes.
- `viewBox` + `preserveAspectRatio="xMidYMid meet"`. Width 100% of its column.
- Strokes `currentColor` or explicit `var(--navy)` / `var(--lava)` / `var(--oat)`.
- Square caps (`stroke-linecap="square"`), miter joins — match the logo.
- Avoid filters except a single soft shadow on a mockup frame.
- Keep node count low (4–8). Databricks diagrams are sparse.

## Anti-patterns (reject in review)

- Text loop rail: `Data → Propose → Approve → Act` as the graphic
- Numbered 01 / 02 / 03 badges as decoration
- Lucide icons in identical rounded squares
- Mesh gradients, glassmorphism, particle-js wallpaper
- Replacing Navy structure with purple “AI” glow
- Screenshot of JSON / notebook as the only visual (workspace mockup must show **objects and links**, human language)

## Implementation sketch

```html
<div class="hero-split">
  <div class="hero-copy">…</div>
  <figure class="hero-visual">
    <!-- inline SVG cycle; CSS animates .token along #loop-path -->
  </figure>
</div>
```

```css
.hero-split {
  display: grid;
  grid-template-columns: minmax(0, 36rem) minmax(20rem, 1fr);
  gap: 48px;
  align-items: center;
}
@media (max-width: 1023px) {
  .hero-split { grid-template-columns: 1fr; }
}
```

Motion for paths and tokens: [motion.md](motion.md).
