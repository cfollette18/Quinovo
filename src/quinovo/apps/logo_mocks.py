"""Standalone page that shows the ten Quinovo logo studies as images."""

from __future__ import annotations

from dataclasses import dataclass

from quinovo.apps.landing_graphics import BRICKS


@dataclass(frozen=True)
class LogoMock:
    number: int
    name: str
    filename: str


LOGO_MOCKS: tuple[LogoMock, ...] = (
    LogoMock(1, "Knot Q", "quinovo_logo_01_knot_q.png"),
    LogoMock(2, "Primitives compass", "quinovo_logo_02_compass_primitives.png"),
    LogoMock(3, "Ontology lattice", "quinovo_logo_03_ontology_lattice.png"),
    LogoMock(4, "Stamp / seal", "quinovo_logo_04_stamp_seal.png"),
    LogoMock(5, "Split brick Q", "quinovo_logo_05_split_brick_q.png"),
    LogoMock(6, "Loop arrow", "quinovo_logo_06_loop_arrow.png"),
    LogoMock(7, "Negative-space Q", "quinovo_logo_07_negative_space_q.png"),
    LogoMock(8, "Twin nodes + verb", "quinovo_logo_08_twin_nodes_verb.png"),
    LogoMock(9, "Folded ribbon", "quinovo_logo_09_folded_ribbon.png"),
    LogoMock(10, "Monogram lockup", "quinovo_logo_10_monogram_lockup.png"),
)


def _card(mock: LogoMock) -> str:
    src = f"/assets/logo-mocks/{mock.filename}"
    return f"""
      <figure class="mock-card">
        <img src="{src}" alt="{mock.number}. {mock.name}" width="1024" height="1024"/>
        <figcaption>
          <span class="mock-num">{mock.number}</span>
          <span class="mock-name">{mock.name}</span>
        </figcaption>
      </figure>"""


def logo_mocks_html() -> str:
    cards = "".join(_card(mock) for mock in LOGO_MOCKS)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Logo mocks — Quinovo</title>
  <meta name="theme-color" content="#f9f7f4"/>
  <meta name="description" content="Ten Quinovo mark studies for review."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap"/>
  <link rel="stylesheet" href="/assets/landing.css"/>
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"/>
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"/>
  <link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png"/>
  <style>
    .mocks-page {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 48px 32px 96px;
    }}
    .mocks-page h1 {{
      margin: 0 0 8px;
      color: var(--navy);
      font: 500 clamp(32px, 4vw, 48px)/1.15 var(--font);
      letter-spacing: -0.03em;
    }}
    .mocks-lede {{
      margin: 0 0 40px;
      max-width: 42rem;
      color: var(--muted);
    }}
    .mocks-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 28px 24px;
    }}
    .mock-card {{
      margin: 0;
      background: var(--white);
      border: 1px solid var(--border);
    }}
    .mock-card img {{
      display: block;
      width: 100%;
      height: auto;
      aspect-ratio: 1;
      object-fit: contain;
      background: var(--oat-mid);
    }}
    .mock-card figcaption {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      padding: 14px 16px 16px;
      color: var(--navy);
    }}
    .mock-num {{
      font: 500 15px/1.2 var(--mono);
      color: var(--lava);
      min-width: 1.5ch;
    }}
    .mock-name {{
      font: 500 18px/1.3 var(--font);
    }}
    @media (max-width: 720px) {{
      .mocks-page {{ padding: 32px 16px 64px; }}
      .mocks-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site">
    <div class="site-inner">
      <a class="brand" href="/">{BRICKS}<span class="brand-name">quinovo</span></a>
      <nav class="site-nav" aria-label="Logo mocks">
        <a href="/">Back to home</a>
      </nav>
    </div>
  </header>
  <main id="main" class="mocks-page">
    <h1>Logo mocks</h1>
    <p class="mocks-lede">Ten mark studies. Each card is one image with its number and name.</p>
    <div class="mocks-grid">
{cards}
    </div>
  </main>
</body>
</html>
"""
