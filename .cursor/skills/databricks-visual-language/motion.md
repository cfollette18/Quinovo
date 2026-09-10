# Motion (Databricks.com → Quinovo)

Infrastructure software signals reliability by **not bouncing**. Match Databricks timing; keep Lava / Navy / Oat.

## Tokens

```css
:root {
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-emphasized: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);
  --motion-fast: 150ms;
  --motion-standard: 240ms;
  --motion-slow: 320ms;
}
```

No spring, no overshoot, no bounce. Data pipelines do not bounce.

## Page

- Section enter: **once**, `IntersectionObserver`, fade + `translateY(24px)` → 0 over `--motion-slow` / `--ease-emphasized`.
- Stagger **children of one grid** by 80ms. Do not give every section its own fade-up; that reads as generic AI landing pages.
- Hero graphic: one idle loop (token on path, 8–12s `linear` infinite) **or** mockup parallax `translateY` of about **-2%** of scroll within the hero. Not both at full intensity.
- Decorative loops need a **pause control** (button or `animation-play-state`) for accessibility.

## Chrome

| Event | Motion |
|---|---|
| Button hover (Lava) | `filter: brightness(1.08)` over `--motion-fast`. No translate. |
| Button active | `--lava-pressed`, optional `translateY(1px)` |
| Ghost hover | Fill navy, text oat, `--motion-fast` |
| Card hover | `translateY(-2px)`, shadow `0 4px 12px` → `0 12px 32px rgba(27,49,57,.12)`, `--motion-standard` |
| Focus | 2–3px Lava ring, offset 2px |
| Tabs on navy band | Crossfade diagram 240ms opacity. No slide-all-cards. |
| FAQ / agent `<details>` | Chevron rotate 150ms; height can be instant |
| Count-up stats | Only if a real number is on screen; respect reduced motion (show final value) |

## Diagrams

- Path flow: `stroke-dashoffset` over 2–4s linear, infinite, paused when off-screen or reduced-motion.
- Token on path: `offset-path: path(...)` + `offset-distance` 0% → 100%, 8–12s.
- Tab change: swap which node is Lava; 240ms fill/stroke transition.
- Draw-on once at first intersection (dashoffset 100% → 0 over 800ms) then switch to idle flow.

## Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
  }
  .hero-visual, .arch-diagram, .card {
    transform: none !important;
    filter: none !important;
  }
  /* Optional: allow 100ms opacity-only on buttons */
}
```

Freeze diagrams at a complete, readable rest pose (all nodes visible, token at Approve or similar). Disable parallax and hover lift.

## Do not

- Animate opacity+slide on every card independently on load.
- Use Lottie of generic isometric cities.
- Autoplay video with sound.
- Infinite attention-grabbing pulse on CTAs.
- `transition: all`.
