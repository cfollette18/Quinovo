"""Inline SVG / HTML diagrams for the public landing page.

Dashboard mockup matches the Chat workspace (composer, tool steps, a short
answer). The loop is the Quinovo mark exploded: four square stations on a
diamond around a mini graph.
"""

from __future__ import annotations

LAVA = "#FF3621"
NAVY = "#1B3139"
NAVY_600 = "#1B5162"
NAVY_900 = "#0B2026"
OAT = "#F9F7F4"
OAT_MID = "#EEEDE9"
WHITE = "#FFFFFF"
MUTED = "#5F737D"
BORDER = "#E4E2DD"
BLUE = "#2272B4"
GREEN = "#00A972"
YELLOW = "#FFAB00"
MAROON = "#98102A"
EDGE = "#C4CCD6"

_FONT = "DM Sans, Helvetica Neue, Arial, sans-serif"

BRICKS = (
    '<svg viewBox="0 0 64 64" width="28" height="28" role="img" aria-label="Quinovo">'
    f'<path d="M32 14 L50 32 L32 50 L14 32 Z" fill="none" stroke="{NAVY}" '
    'stroke-width="3.5" stroke-linejoin="miter"/>'
    f'<rect x="27" y="9" width="10" height="10" fill="{LAVA}"/>'
    f'<rect x="45" y="27" width="10" height="10" fill="{NAVY}"/>'
    f'<rect x="27" y="45" width="10" height="10" fill="{NAVY}"/>'
    f'<rect x="9" y="27" width="10" height="10" fill="{NAVY}"/>'
    f'<path d="M40 40 L56 56" fill="none" stroke="{NAVY}" stroke-width="4" '
    'stroke-linecap="square"/>'
    "</svg>"
)

BRICKS_ON_DARK = (
    '<svg viewBox="0 0 64 64" width="28" height="28" role="img" aria-label="Quinovo">'
    f'<path d="M32 14 L50 32 L32 50 L14 32 Z" fill="none" stroke="{OAT}" '
    'stroke-width="3.5" stroke-linejoin="miter"/>'
    f'<rect x="27" y="9" width="10" height="10" fill="{LAVA}"/>'
    f'<rect x="45" y="27" width="10" height="10" fill="{OAT}"/>'
    f'<rect x="27" y="45" width="10" height="10" fill="{OAT}"/>'
    f'<rect x="9" y="27" width="10" height="10" fill="{OAT}"/>'
    f'<path d="M40 40 L56 56" fill="none" stroke="{OAT}" stroke-width="4" '
    'stroke-linecap="square"/>'
    "</svg>"
)

# Same marks as the workspace rail (stroke icons, currentColor).
_RAIL = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><path d="M4 5h16v11H8l-4 3V5z"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/>'
    '<rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><path d="M12 3 6.5 12h5L10 21l7.5-10h-5L12 3z"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><path d="M4 7h10M4 12h10M4 17h7"/><circle cx="19" cy="7" r="2"/>'
    '<circle cx="19" cy="17" r="2"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><path d="M8 6h12M8 12h12M8 18h12"/>'
    '<circle cx="4" cy="6" r="1.2" fill="currentColor" stroke="none"/>'
    '<circle cx="4" cy="12" r="1.2" fill="currentColor" stroke="none"/>'
    '<circle cx="4" cy="18" r="1.2" fill="currentColor" stroke="none"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><path d="M3 11 12 6l9 5-9 5-9-5z"/>'
    '<path d="M7 13.2v4c0 .9 2.2 1.8 5 1.8s5-1 5-1.8v-4"/><path d="M21 11v5"/></svg>',
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7.5"/></svg>',
)


def _card(
    x: float,
    y: float,
    swatch: str,
    kind: str,
    label: str,
    *,
    w: float = 160,
    h: float = 50,
    selected: bool = False,
    pending: bool = False,
) -> str:
    stroke = LAVA if selected else BORDER
    sw = 2 if selected else 1
    fill = WHITE
    dot = ""
    if pending:
        dot = (
            f'<circle cx="{x + w - 12}" cy="{y + 12}" r="4" fill="{YELLOW}">'
            "<title>Needs a look</title></circle>"
        )
    return (
        f'<g class="mock-node{" selected" if selected else ""}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"/>'
        f'<rect x="{x}" y="{y}" width="5" height="{h}" fill="{swatch}"/>'
        f'<text x="{x + 16}" y="{y + 18}" fill="{MUTED}" font-size="10" '
        f'font-family="{_FONT}">{kind}</text>'
        f'<text x="{x + 16}" y="{y + 36}" fill="{NAVY}" font-size="13" '
        f'font-weight="500" font-family="{_FONT}">{label}</text>'
        f"{dot}</g>"
    )


def _edge(x1: float, y1: float, x2: float, y2: float, label: str, *, hot: bool = False) -> str:
    color = NAVY_600 if hot else EDGE
    width = 1.8 if hot else 1.4
    cls = "flow-edge hot" if hot else "flow-edge"
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 8
    opacity = "1" if hot else "0.85"
    return (
        f'<g class="mock-edge{" on" if hot else ""}">'
        f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="square"/>'
        f'<text x="{mx}" y="{my}" text-anchor="middle" fill="{MUTED}" font-size="10" '
        f'font-family="{_FONT}" opacity="{opacity}">{label}</text>'
        "</g>"
    )


def _pause_btn() -> str:
    return (
        '<button class="motion-pause" type="button" data-motion-pause '
        'aria-pressed="false">Pause motion</button>'
    )


def hero_workspace_mockup() -> str:
    """Framed Chat, stripped to one confident composition.

    A user question, one tool step with a Lava square token, a short answer,
    and the composer. The rail and topbar stay so the frame still reads as
    the real product.
    """
    navs = "".join(
        f'<span class="mock-nav{" on" if i == 0 else ""}">{icon}</span>'
        for i, icon in enumerate(_RAIL[:5])
    )
    return f"""
<figure class="hero-visual" aria-hidden="true">
  <div class="mock-workspace">
    <div class="mock-rail">
      <span class="mock-brand">{BRICKS}</span>
      <div class="mock-navs">{navs}</div>
    </div>
    <div class="mock-body">
      <div class="mock-topbar">
        <span class="mock-wordmark">quinovo</span>
        <span class="mock-pack">Example commerce</span>
        <span class="mock-avatar">L</span>
      </div>
      <div class="mock-page mock-chat-page">
        <div class="mock-chat">
          <div class="mock-chat-user">Where is package 1Z999?</div>
          <div class="mock-tool">
            <span class="mock-tool-icon" aria-hidden="true"></span>
            <span class="mock-tool-verb">Calling Read</span>
            <span class="mock-tool-target">Package 1Z999</span>
            <span class="mock-tool-token"></span>
          </div>
          <p class="mock-chat-answer">Destined for Bob. In transit, carrying cherry lipstick.</p>
        </div>
        <div class="mock-composer">
          <span>Ask the graph</span>
          <span class="mock-send"></span>
        </div>
      </div>
    </div>
  </div>
  {_pause_btn()}
  <figcaption class="sr-only">The Chat workspace: a question about a package, a lookup step, and a plain-language answer.</figcaption>
</figure>
"""


def _station(x: int, y: int, w: int, h: int, stage: str, title: str, sub: str, *, lava: bool = False) -> str:
    fill = LAVA if lava else NAVY_900
    stroke = OAT if lava else OAT_MID
    title_fill = WHITE if lava else OAT
    sub_fill = "rgba(255,255,255,0.85)" if lava else MUTED
    return (
        f'<g class="station station-{stage}">'
        f'<rect class="station-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="2" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        f'<text x="{x + 16}" y="{y + 28}" fill="{title_fill}" font-size="14" font-weight="500" '
        f'font-family="{_FONT}">{title}</text>'
        f'<text x="{x + 16}" y="{y + 48}" fill="{sub_fill}" font-size="12" '
        f'font-family="{_FONT}">{sub}</text>'
        "</g>"
    )


def arch_diagram() -> str:
    """Diamond loop, four stations, one stroke, a returning arrow.

    The kernel at the center is the Quinovo mark itself (diamond ring + four
    squares, top one Lava) — the brand primitive at page scale, not a busy
    mini graph. A Lava token travels the loop; the active station lights up.
    """
    # Center mark: the Quinovo brick at diagram scale.
    cx, cy = 520, 200
    mark = (
        f'<g class="arch-mark">'
        # Diamond ring
        f'<path d="M{cx} {cy-46} L{cx+46} {cy} L{cx} {cy+46} L{cx-46} {cy} Z" '
        f'fill="none" stroke="{OAT_MID}" stroke-width="2" stroke-linejoin="miter"/>'
        # Four cardinal squares, top one Lava
        f'<rect x="{cx-5}" y="{cy-56}" width="10" height="10" fill="{LAVA}"/>'
        f'<rect x="{cx+46}" y="{cy-5}" width="10" height="10" fill="{OAT}"/>'
        f'<rect x="{cx-5}" y="{cy+46}" width="10" height="10" fill="{OAT}"/>'
        f'<rect x="{cx-56}" y="{cy-5}" width="10" height="10" fill="{OAT}"/>'
        # Q-tail
        f'<path d="M{cx+18} {cy+18} L{cx+34} {cy+34}" fill="none" '
        f'stroke="{OAT}" stroke-width="4" stroke-linecap="square"/>'
        f'<text x="{cx}" y="{cy+78}" text-anchor="middle" fill="{MUTED}" '
        f'font-size="11" font-weight="500" font-family="{_FONT}">Kernel · Graph</text>'
        f"</g>"
    )
    return f"""
<figure class="arch-figure">
  <svg class="arch-diagram" viewBox="0 0 1040 400" xmlns="http://www.w3.org/2000/svg"
       role="img" aria-labelledby="arch-title">
    <title id="arch-title">Data lands on the graph. Quinovo proposes. You approve. Actions write back.</title>
    <!-- One stroke: the diamond loop -->
    <path class="loop-ring" d="M520 52 L910 200 L520 348 L130 200 Z"
          fill="none" stroke="{OAT_MID}" stroke-width="1.6" stroke-linejoin="miter"/>
    <path class="flow-pipe loop-path" d="M520 52 L910 200 L520 348 L130 200 Z"
          fill="none" stroke="{LAVA}" stroke-width="2" stroke-linejoin="miter"
          stroke-linecap="square"/>
    <!-- Returning arrowhead at the top station (Data) -->
    <path class="loop-arrow" d="M534 60 L520 52 L526 66" fill="none"
          stroke="{LAVA}" stroke-width="2" stroke-linecap="square"
          stroke-linejoin="miter"/>
    {mark}
    {_station(80, 164, 140, 72, "logic", "Propose", "rules from data")}
    {_station(430, 16, 180, 72, "approve", "You approve", "below 0.8 waits", lava=True)}
    {_station(820, 164, 140, 72, "action", "Act", "write back")}
    {_station(430, 312, 180, 72, "data", "Data in", "objects and links")}
    <rect class="arch-token" x="0" y="0" width="10" height="10" fill="{LAVA}"/>
  </svg>
  {_pause_btn()}
</figure>"""


def _mini_svg(body: str, view: str = "0 0 320 140", *, kind: str = "") -> str:
    cls = f"why-svg why-svg-{kind}" if kind else "why-svg"
    return (
        f'<svg class="{cls}" viewBox="{view}" xmlns="http://www.w3.org/2000/svg" '
        'aria-hidden="true" focusable="false">'
        f"{body}</svg>"
    )


def why_graphic(key: str) -> str:
    """Card-header diagram. Each one is a slice of the real product."""
    if key == "discovered":
        # Three lanes, three nodes, two edges that assemble with a snap.
        return _mini_svg(
            f'<rect x="8" y="10" width="96" height="120" fill="{WHITE}"/>'
            f'<rect x="112" y="10" width="96" height="120" fill="rgba(255,255,255,0.5)"/>'
            f'<rect x="216" y="10" width="96" height="120" fill="{WHITE}"/>'
            f'<line x1="112" y1="14" x2="112" y2="126" stroke="{BORDER}"/>'
            f'<line x1="216" y1="14" x2="216" y2="126" stroke="{BORDER}"/>'
            f'<text x="16" y="26" fill="{NAVY}" font-size="10" font-weight="500" font-family="{_FONT}">Package</text>'
            f'<text x="120" y="26" fill="{NAVY}" font-size="10" font-weight="500" font-family="{_FONT}">Person</text>'
            f'<text x="224" y="26" fill="{NAVY}" font-size="10" font-weight="500" font-family="{_FONT}">Product</text>'
            f'<g class="disc-node disc-n1">{_card(16, 46, LAVA, "Package", "1Z999", w="80", h="40", selected=True)}</g>'
            f'<g class="disc-node disc-n2">{_card(120, 46, BLUE, "Person", "Bob", w="80", h="40")}</g>'
            f'<g class="disc-node disc-n3">{_card(224, 46, GREEN, "Product", "Lipstick", w="80", h="40")}</g>'
            f'<line class="disc-edge disc-e1" x1="96" y1="66" x2="120" y2="66" '
            f'stroke="{NAVY}" stroke-width="1.6" stroke-linecap="square"/>'
            f'<line class="disc-edge disc-e2" x1="200" y1="66" x2="224" y2="66" '
            f'stroke="{NAVY}" stroke-width="1.6" stroke-linecap="square"/>',
            kind="discovered",
        )
    if key == "mcp":
        return _mini_svg(
            f'<g class="mcp-agents">'
            f'<rect x="16" y="28" width="64" height="28" rx="2" fill="{WHITE}" stroke="{BORDER}"/>'
            f'<text x="48" y="47" text-anchor="middle" fill="{NAVY}" font-size="11" font-family="{_FONT}">Cursor</text>'
            f'<rect x="16" y="64" width="64" height="28" rx="2" fill="{WHITE}" stroke="{BORDER}"/>'
            f'<text x="48" y="83" text-anchor="middle" fill="{NAVY}" font-size="11" font-family="{_FONT}">Claude</text>'
            f"</g>"
            f'<path class="mcp-link mcp-l1" d="M80 42 H128" stroke="{NAVY}" stroke-width="1.6" stroke-linecap="square"/>'
            f'<path class="mcp-link mcp-l2" d="M80 78 H128" stroke="{EDGE}" stroke-width="1.4" stroke-linecap="square"/>'
            f'<rect class="mcp-join" x="122" y="56" width="10" height="10" fill="{LAVA}"/>'
            f'<g class="mcp-kernel">{_card(140, 44, LAVA, "Package", "1Z999", w="160", h="50", selected=True)}</g>',
            kind="mcp",
        )
    if key == "specialists":
        # One train set; a seed grows and three copies land in the adjacent sets.
        return _mini_svg(
            f'<rect x="12" y="16" width="100" height="108" fill="{WHITE}" stroke="{LAVA}" stroke-width="2"/>'
            f'<rect x="122" y="16" width="90" height="108" fill="{OAT_MID}" opacity="0.7"/>'
            f'<rect x="220" y="16" width="90" height="108" fill="{OAT_MID}" opacity="0.45"/>'
            f'<text x="24" y="36" fill="{NAVY}" font-size="11" font-weight="500" font-family="{_FONT}">Train set</text>'
            f'{_card(24, 48, LAVA, "Package", "1Z999", w="76", h="36")}'
            f'{_card(24, 90, LAVA, "Package", "UPS001", w="76", h="28")}'
            f'<rect class="spec-seed" x="94" y="22" width="10" height="10" fill="{LAVA}"/>'
            f'<rect class="spec-clone spec-c1" x="154" y="52" width="10" height="10" fill="{NAVY}"/>'
            f'<rect class="spec-clone spec-c2" x="178" y="72" width="10" height="10" fill="{LAVA}"/>'
            f'<rect class="spec-clone spec-c3" x="252" y="62" width="10" height="10" fill="{NAVY}"/>',
            kind="specialists",
        )
    if key == "hitl":
        return _mini_svg(
            f'<rect x="24" y="18" width="272" height="104" rx="4" fill="{WHITE}" stroke="{BORDER}"/>'
            f'<text x="40" y="40" fill="{LAVA}" font-size="11" font-weight="500" font-family="{_FONT}">Needs a look</text>'
            f'<text x="40" y="62" fill="{NAVY}" font-size="14" font-weight="500" font-family="{_FONT}">Suggested warehouse</text>'
            f'<circle class="hitl-dot" cx="276" cy="36" r="4" fill="{YELLOW}"/>'
            f'<rect x="40" y="78" width="88" height="28" rx="2" fill="{LAVA}"/>'
            f'<text x="84" y="96" text-anchor="middle" fill="{WHITE}" font-size="12" font-weight="500" font-family="{_FONT}">Approve</text>'
            f'<polyline class="hitl-check" points="268,36 274,42 286,28" fill="none" '
            f'stroke="{NAVY}" stroke-width="2.2" stroke-linecap="square" stroke-linejoin="miter"/>'
            f'<rect x="136" y="78" width="96" height="28" rx="2" fill="none" stroke="{NAVY}" stroke-width="1"/>'
            f'<text x="184" y="96" text-anchor="middle" fill="{NAVY}" font-size="12" font-weight="500" font-family="{_FONT}">Turn down</text>',
            kind="hitl",
        )
    if key == "record":
        return _mini_svg(
            f'<g class="rec-kernel">'
            f'<rect x="10" y="14" width="168" height="112" fill="{WHITE}" stroke="{BORDER}"/>'
            f'{_card(22, 30, LAVA, "Package", "1Z999", w="70", h="36")}'
            f'{_card(100, 30, BLUE, "Person", "Bob", w="66", h="36")}'
            f'<line x1="92" y1="48" x2="100" y2="48" stroke="{NAVY}" stroke-width="1.5" stroke-linecap="square"/>'
            f'<rect class="rec-tick" x="18" y="20" width="8" height="8" fill="{LAVA}"/>'
            f"</g>"
            f'<g class="rec-dash">'
            f'<rect class="rec-bar rec-bar-1" x="198" y="68" width="14" height="42" fill="{NAVY}"/>'
            f'<rect class="rec-bar rec-bar-2" x="218" y="48" width="14" height="62" fill="{NAVY}"/>'
            f'<rect class="rec-bar rec-bar-3" x="238" y="34" width="14" height="76" fill="{LAVA}"/>'
            f'<rect class="rec-bar rec-bar-4" x="258" y="56" width="14" height="54" fill="{NAVY}"/>'
            f"</g>"
            f'<g class="rec-write">'
            f'<path class="rec-arrow" d="M178 88 H196" stroke="{NAVY}" stroke-width="1.5" stroke-linecap="square"/>'
            f"</g>",
            kind="record",
        )
    return _mini_svg(
        f'<g class="sec-lock">'
        f'<path class="sec-shackle" d="M124 54 V36 a36 26 0 0 1 72 0 V54" fill="none" '
        f'stroke="{NAVY}" stroke-width="5" stroke-linecap="square"/>'
        f'<rect class="sec-body" x="108" y="52" width="104" height="72" rx="2" fill="{WHITE}" '
        f'stroke="{NAVY}" stroke-width="2"/>'
        f'{_card(116, 60, MAROON, "Actor", "Approver", w="88", h="40")}'
        f'<rect class="sec-key" x="152" y="106" width="16" height="8" fill="{LAVA}"/>'
        f"</g>",
        kind="security",
    )


def primitive_graphic(name: str) -> str:
    if name == "Data":
        body = (
            f'{_card(16, 16, LAVA, "Package", "1Z999", w="120", h="40")}'
            f'{_card(16, 68, BLUE, "Person", "Bob", w="120", h="40")}'
            f'<line class="flow-edge" x1="76" y1="56" x2="76" y2="68" stroke="{NAVY}" stroke-width="1.5"/>'
        )
    elif name == "Logic":
        body = (
            f'<rect x="16" y="28" width="88" height="36" rx="2" fill="{WHITE}" stroke="{BORDER}"/>'
            f'<text x="60" y="51" text-anchor="middle" fill="{NAVY}" font-size="12" font-family="{_FONT}">If late</text>'
            f'<path d="M104 46 H136" stroke="{NAVY}" stroke-width="1.6" stroke-linecap="square"/>'
            f'<rect x="136" y="28" width="100" height="36" rx="2" fill="{WHITE}" stroke="{LAVA}" stroke-width="2"/>'
            f'<text x="186" y="51" text-anchor="middle" fill="{NAVY}" font-size="12" font-family="{_FONT}">then notify</text>'
        )
    elif name == "Action":
        body = (
            f'{_card(12, 36, GREEN, "Product", "Lipstick", w="110", h="44")}'
            f'<path class="flow-edge" d="M122 58 H168" stroke="{NAVY}" stroke-width="1.6" stroke-linecap="square"/>'
            f'<rect x="168" y="40" width="72" height="36" rx="2" fill="{NAVY}"/>'
            f'<text x="204" y="62" text-anchor="middle" fill="{OAT}" font-size="12" font-family="{_FONT}">write</text>'
        )
    else:
        body = (
            f'<rect x="40" y="16" width="168" height="96" rx="2" fill="none" stroke="{NAVY}" stroke-width="2"/>'
            f'<rect x="108" y="8" width="32" height="14" fill="{LAVA}"/>'
            f'{_card(64, 40, MAROON, "Right", "approve", w="120", h="44")}'
        )
    return (
        f'<svg class="prim-svg" viewBox="0 0 256 128" xmlns="http://www.w3.org/2000/svg" '
        f'aria-hidden="true" focusable="false">{body}</svg>'
    )
