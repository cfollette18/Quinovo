"""Shared Databricks-styled workspace chrome for HTTP pages."""

from __future__ import annotations

import html
from typing import Any

FONTS = (
    "https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@"
    "0,9..40,400;0,9..40,500;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap"
)

BRICKS = """<svg viewBox="0 0 64 64" width="28" height="28" role="img" aria-label="Quinovo">
  <path d="M32 14 L50 32 L32 50 L14 32 Z" fill="none" stroke="#1B3139" stroke-width="3.5" stroke-linejoin="miter"/>
  <rect x="27" y="9"  width="10" height="10" fill="#FF3621"/>
  <rect x="45" y="27" width="10" height="10" fill="#1B3139"/>
  <rect x="27" y="45" width="10" height="10" fill="#1B3139"/>
  <rect x="9"  y="27" width="10" height="10" fill="#1B3139"/>
  <path d="M40 40 L56 56" fill="none" stroke="#1B3139" stroke-width="4" stroke-linecap="square"/>
</svg>"""

_ICONS = {
    "twin": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 20 8v8l-8 5-8-5V8z"/><path d="M12 8v13"/><path d="m4.5 10 7.5 4 7.5-4"/></svg>""",
    "graph": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="6" cy="7" r="2.2"/><circle cx="18" cy="7" r="2.2"/><circle cx="12" cy="17" r="2.2"/><path d="M8 8.2 10.4 15M16 8.2 13.6 15"/></svg>""",
    "schema": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/></svg>""",
    "logic": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 6.5 12h5L10 21l7.5-10h-5L12 3z"/></svg>""",
    "audit": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1.2" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r="1.2" fill="currentColor" stroke="none"/></svg>""",
    "train": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 11 12 6l9 5-9 5-9-5z"/><path d="M7 13.2v4c0 .9 2.2 1.8 5 1.8s5-1 5-1.8v-4"/><path d="M21 11v5"/></svg>""",
    "settings": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""",
    "sources": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7h10M4 12h10M4 17h7"/><circle cx="19" cy="7" r="2"/><circle cx="19" cy="17" r="2"/></svg>""",
}

# Rail order matches docs/conventions.md. Settings stays with the other
# destinations, not pinned off-screen at the bottom of the rail.
_NAV: list[tuple[str, str, str]] = [
    ("twin", "/twin", "Twin"),
    ("graph", "/graph", "Graph"),
    ("schema", "/catalog", "Catalog"),
    ("logic", "/inference", "Inference"),
    ("sources", "/sources", "Sources"),
    ("audit", "/audit", "Audit"),
    ("train", "/train", "Train"),
    ("settings", "/settings", "Settings"),
]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def json_panel(data: Any, label: str = "JSON") -> str:
    """No-op. The Quinovo frontend never shows raw JSON to users.

    Kept as an empty-string stub so any unmigrated caller renders nothing
    instead of crashing. The raw contract remains available at /contract.json
    for power users; the UI itself stays human-first.
    """
    return ""


def nav_items() -> list[tuple[str, str, str]]:
    """Left-rail destinations. Settings is always present; Train is kept if added."""
    items = list(_NAV)
    keys = {key for key, _href, _label in items}
    if "train" in _ICONS and "train" not in keys:
        insert_at = next(
            (index for index, (key, _href, _label) in enumerate(items) if key == "settings"),
            len(items),
        )
        items.insert(insert_at, ("train", "/train", "Train"))
    if "settings" not in {key for key, _href, _label in items}:
        items.append(("settings", "/settings", "Settings"))
    return items


def workspace_tabs(current: str) -> str:
    bits = []
    for key, href, label in nav_items():
        on = "on" if current == key else ""
        current_attr = ' aria-current="page"' if current == key else ""
        bits.append(
            f'<a class="tab {on}" href="{esc(href)}"{current_attr}>{esc(label)}</a>'
        )
    return f'<nav class="tabs" aria-label="Workspace">{"".join(bits)}</nav>'


def empty_state(title: str, body: str, href: str = "", action: str = "") -> str:
    """Composed empty state: what this place is, plus one next action."""
    cta = ""
    if href and action:
        cta = (
            f'<p class="empty-action">'
            f'<a class="btn btn-ghost" href="{esc(href)}">{esc(action)}</a>'
            f"</p>"
        )
    return (
        f'<div class="empty-state">'
        f'<p class="empty-title">{esc(title)}</p>'
        f'<p class="empty">{esc(body)}</p>'
        f"{cta}"
        f"</div>"
    )


def page_head(
    crumb: str,
    title: str,
    meta: str,
    current: str,
    *,
    actions: str = "",
    title_html: bool = False,
) -> str:
    heading = title if title_html else f"<h1>{esc(title)}</h1>"
    actions_html = f'<div class="page-actions">{actions}</div>' if actions else ""
    return f"""
<div class="page-head">
  <p class="crumbs"><span>Workspace</span><span class="here">{esc(crumb)}</span></p>
  <div class="page-head-row">
    <div>
      {heading}
      <p class="meta">{meta}</p>
    </div>
    {actions_html}
  </div>
  {workspace_tabs(current)}
</div>"""


_HITL = """
<script>
document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-hitl]");
  if (!btn) return;
  ev.preventDefault();
  const kind = btn.dataset.hitl;
  const id = btn.dataset.id;
  const note = document.getElementById("note") || document.getElementById("action-note");
  const routes = {
    approve_proposal: "/proposals/" + id + "/approve",
    reject_proposal: "/proposals/" + id + "/reject",
    approve_fact: "/inference/facts/" + id + "/approve",
    approve_action: "/pending-actions/" + id + "/approve",
    reject_action: "/pending-actions/" + id + "/reject",
  };
  const url = routes[kind];
  if (!url) return;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor: "human" }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (note) {
      note.className = "notice err";
      note.textContent = data.detail || res.status;
    }
    return;
  }
  location.reload();
});
</script>
"""


def wrap(
    title: str,
    body: str,
    *,
    nav: str = "graph",
    pack_name: str = "",
    extra_head: str = "",
    extra_script: str = "",
) -> str:
    items = []
    for key, href, label in nav_items():
        on = "on" if nav == key else ""
        current_attr = ' aria-current="page"' if nav == key else ""
        icon = _ICONS.get(key, "")
        items.append(
            f'<a class="nav {on}" href="{esc(href)}" title="{esc(label)}" '
            f'aria-label="{esc(label)}"{current_attr}>{icon}</a>'
        )
    rail = "\n      ".join(items)
    pack = esc(pack_name)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="theme-color" content="#f9f7f4"/>
  <meta name="description" content="Quinovo workspace — approve what the loop is not sure about."/>
  <title>{esc(title)}</title>
  <link rel="stylesheet" href="{FONTS}"/>
  <link rel="stylesheet" href="/assets/chrome.css"/>
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"/>
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"/>
  <link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png"/>
  {extra_head}
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <aside class="rail">
    <a class="brand" href="/" title="Quinovo" aria-label="Quinovo home">{BRICKS}</a>
    <nav aria-label="Workspace">
      {rail}
    </nav>
  </aside>
  <div class="workspace">
    <header class="topbar">
      <p class="wordmark">quinovo</p>
      <div class="search-wrap">
        <label class="sr-only" for="q">Search by name</label>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20 16.5 16.5"/></svg>
        <input id="q" type="search" placeholder="Search by name" autocomplete="off"/>
      </div>
      <div class="top-actions">
        <span class="pack-label" id="pack-name">{pack}</span>
        <span class="avatar" title="local" aria-label="Local user">L</span>
      </div>
    </header>
    <main id="main" class="workspace-main">
    {body}
    </main>
  </div>
  {_HITL}
  <script>
  (function () {{
    const q = document.getElementById("q");
    if (!q) return;
    q.addEventListener("keydown", (ev) => {{
      if (ev.key !== "Enter" || q.dataset.local === "1") return;
      const v = q.value.trim();
      location.href = v ? "/graph?q=" + encodeURIComponent(v) : "/graph";
    }});
  }})();
  </script>
  {extra_script}
</body>
</html>"""
