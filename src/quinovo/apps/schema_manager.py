"""Catalog: topics as nested baskets, then kinds and actions in plain language."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from quinovo.apps.chrome import empty_state, esc, page_head, wrap
from quinovo.apps.humanize import (
    catalog_action_blurb,
    catalog_kind_blurb,
    catalog_kind_name,
    title_case,
)
from quinovo.language.models import Ontology

_DIAGRAM = """
<svg class="catalog-diagram" viewBox="0 0 280 168" width="280" height="168" role="img" aria-label="A topic holds subtopics, which hold similar things">
  <rect x="8" y="18" width="168" height="132" fill="#FFFFFF" stroke="#1B3139" stroke-width="2"/>
  <text x="20" y="40" fill="#1B3139" font-size="12" font-family="DM Sans, Helvetica Neue, Arial, sans-serif">Fruit</text>
  <rect x="24" y="52" width="136" height="84" fill="#F9F7F4" stroke="#1B3139" stroke-width="1.5"/>
  <text x="36" y="74" fill="#5F737D" font-size="11" font-family="DM Sans, Helvetica Neue, Arial, sans-serif">Tropical fruit</text>
  <rect x="36" y="86" width="112" height="36" fill="#FF3621"/>
  <text x="48" y="108" fill="#fff" font-size="11" font-family="DM Sans, Helvetica Neue, Arial, sans-serif">Orange tropical</text>
  <rect x="192" y="52" width="72" height="20" fill="#1B3139"/>
  <rect x="192" y="80" width="72" height="20" fill="#1B3139"/>
  <rect x="192" y="108" width="72" height="20" fill="#1B5162"/>
</svg>
"""


def _count_line(counts: dict[str, int]) -> str:
    items = int(counts.get("items") or 0)
    subs = int(counts.get("subtopics") or 0)
    item_label = "thing" if items == 1 else "things"
    sub_label = "subtopic" if subs == 1 else "subtopics"
    return f"{items} {item_label} · {subs} {sub_label}"


def _mix_line(counts: dict[str, int]) -> str:
    order = (
        "conversations",
        "facts",
        "memories",
        "to-dos",
        "decisions",
        "open questions",
        "skills",
        "projects",
    )
    bits: list[str] = []
    for key in order:
        n = int(counts.get(key) or 0)
        if n:
            bits.append(f"{n} {key}")
    return " · ".join(bits)


def _tree_items(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    if not nodes:
        return ""
    bits = [f'<ol class="catalog-tree-list" data-depth="{depth}">']
    for node in nodes:
        topic_id = str(node.get("id") or "")
        name = str(node.get("name") or topic_id)
        counts = node.get("counts") or {}
        items = int(counts.get("items") or 0)
        children = node.get("children") or []
        has_kids = " has-children" if children else ""
        bits.append(
            f'<li class="catalog-tree-node{has_kids}" data-id="{esc(topic_id)}" '
            f'data-name="{esc(name.lower())}" data-depth="{depth}">'
            f'<a class="catalog-tree-link" href="#topic-{esc(topic_id)}" '
            f'data-topic="{esc(topic_id)}">'
            f'<span class="catalog-tree-name">{esc(name)}</span>'
            f'<span class="catalog-tree-count">{items}</span>'
            f"</a>"
        )
        bits.append(_tree_items(children, depth + 1))
        bits.append("</li>")
    bits.append("</ol>")
    return "".join(bits)


def _child_chips(node: dict[str, Any]) -> str:
    children = node.get("children") or []
    if not children:
        return ""
    chips = []
    for child in children:
        child_id = str(child.get("id") or "")
        name = str(child.get("name") or child_id)
        chips.append(
            f'<a class="chip" href="#topic-{esc(child_id)}" data-topic="{esc(child_id)}">'
            f"{esc(name)}</a>"
        )
    return (
        '<div class="topic-subtopics">'
        '<p class="section-label">Inside this basket</p>'
        f'<div class="chips">{"".join(chips)}</div>'
        "</div>"
    )


def _flatten(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        out.append(node)
        out.extend(_flatten(node.get("children") or []))
    return out


def _topic_panels(nodes: list[dict[str, Any]]) -> str:
    panels = []
    for index, node in enumerate(_flatten(nodes)):
        topic_id = str(node.get("id") or "")
        name = str(node.get("name") or topic_id)
        description = str(node.get("description") or "").strip()
        if not description:
            description = "Quinovo grouped similar things here so they are easier to find."
        counts = node.get("counts") or {}
        mix = _mix_line(counts)
        on = " on" if index == 0 else ""
        mix_html = f'<p class="meta">{esc(mix)}</p>' if mix else ""
        empty = ""
        if not mix and not (node.get("children") or []):
            empty = (
                "<p class='empty'>Nothing is in this basket yet. "
                "As chats and facts arrive, Quinovo files them here.</p>"
            )
        panels.append(
            f'<article class="topic-panel{on}" id="topic-{esc(topic_id)}" '
            f'data-topic="{esc(topic_id)}">'
            f'<p class="kicker">Topic</p>'
            f"<h2>{esc(name)}</h2>"
            f"<p class='topic-lede'>{esc(description)}</p>"
            f'<p class="topic-counts">{esc(_count_line(counts))}</p>'
            f"{mix_html}"
            f"{_child_chips(node)}"
            f"{empty}"
            '<div class="topic-actions">'
            f'<a class="btn btn-primary" href="/view/Topic/{esc(topic_id)}">Open this topic</a>'
            f'<a class="btn btn-ghost" href="/chat?q={esc(quote(name))}">Ask about this topic</a>'
            "</div>"
            "</article>"
        )
    return "".join(panels)


def _created_notice(created: list[str]) -> str:
    names = [item for item in created if item]
    if not names:
        return ""
    labels = ", ".join(title_case(item) for item in names[:8])
    extra = "" if len(names) <= 8 else f" and {len(names) - 8} more"
    return (
        '<p class="notice" role="status">'
        f"Quinovo just organized {esc(labels)}{esc(extra)} into topic baskets."
        "</p>"
    )


def _topic_section(topics: list[dict[str, Any]]) -> str:
    if not topics:
        return empty_state(
            "No topics yet",
            "A topic is a basket of similar things. Quinovo creates them as it learns — "
            "for example Fruit, then Tropical fruit inside it. Ask it to organize, or "
            "keep working and baskets appear on their own.",
            "",
            "",
        )
    first = topics[0]
    return f"""
<div class="catalog-split">
  <aside class="catalog-nav">
    <label class="sr-only" for="catalog-filter">Filter topics</label>
    <input id="catalog-filter" type="search" placeholder="Find a topic" autocomplete="off"/>
    <nav class="catalog-tree" aria-label="Topics">
      {_tree_items(topics)}
    </nav>
  </aside>
  <div class="catalog-stage" data-first="{esc(str(first.get('id') or ''))}">
    {_topic_panels(topics)}
  </div>
</div>
"""


def _kind_tiles(ontology: Ontology, counts: dict[str, int]) -> str:
    tiles = []
    for item in ontology.object_types:
        n = counts.get(item.api_name, 0)
        obj_label = "item" if n == 1 else "items"
        href = "/chat?q=" + esc(quote(f"Show me every {item.api_name}"))
        if item.api_name == "Topic":
            href = "#topics"
        tiles.append(
            "<a class='tile' href='"
            f"{href}'>"
            "<p class='kicker'>Kind</p>"
            f"<h3>{esc(catalog_kind_name(item.api_name))}</h3>"
            f"<p>{esc(catalog_kind_blurb(item.api_name, item.description))}</p>"
            f"<p class='meta'>{n} {obj_label}</p>"
            "</a>"
        )
    if not tiles:
        return empty_state(
            "No kinds yet",
            "They appear as the loop learns this workspace.",
            "/sources",
            "Add a connection",
        )
    return f'<div class="tiles">{"".join(tiles)}</div>'


def _action_tiles(ontology: Ontology) -> str:
    tiles = []
    for item in ontology.action_types:
        tiles.append(
            f"<div class='tile' data-action='{esc(item.api_name)}'>"
            "<p class='kicker'>Action</p>"
            f"<h3>{esc(title_case(item.api_name))}</h3>"
            f"<p>{esc(catalog_action_blurb(item.description))}</p>"
            "<p class='meta'>Runs after you approve it, unless Quinovo is already sure.</p>"
            "</div>"
        )
    if not tiles:
        return empty_state(
            "No actions yet",
            "Actions show up when Quinovo proposes something you can run.",
            "/inference",
            "Open Inference",
        )
    return f'<div class="tiles">{"".join(tiles)}</div>'


def schema_manager_html(
    ontology: Ontology,
    counts: dict[str, int] | None = None,
    topics: list[dict[str, Any]] | None = None,
    created: list[str] | None = None,
) -> str:
    counts = counts or {}
    topics = topics or []
    created = created or []
    name = ontology.ontology.display_name
    has_topics = any(item.api_name == "Topic" for item in ontology.object_types)
    intro = (
        "A topic is a basket of similar things. Subtopics nest inside — Fruit, then "
        "tropical fruit, then orange tropical fruit. Quinovo groups them as it learns. "
        "You only look and approve."
    )
    organize = ""
    if has_topics:
        organize = (
            '<form method="post" action="/catalog/organize">'
            '<button type="submit" class="btn btn-primary">Organize with AI</button>'
            "</form>"
        )
    topic_block = f"""
  <section class="catalog-hero" id="topics">
    <div class="catalog-hero-copy">
      <p class="kicker">How it works</p>
      <h2>Baskets, not folders you have to build</h2>
      <p>Quinovo watches what comes in and puts similar things together. A Cretex topic can hold MCP servers, technology, and workflows. You do not have to name every basket first.</p>
    </div>
    {_DIAGRAM}
  </section>
  {_created_notice(created)}
  {_topic_section(topics) if has_topics else empty_state(
      "Topics will show up here",
      "When Quinovo learns this workspace, it groups similar things into nested baskets you can browse.",
      "/sources",
      "Add a connection",
  )}
"""
    body = f"""
{page_head(
    "Catalog",
    "Catalog",
    intro,
    "schema",
    actions=organize,
)}
<div class="page">
  <div class="doc catalog-page">
{topic_block}
    <h2 id="types">Kinds of things</h2>
    <p class="meta">These are the shapes Quinovo already understands. Open one to see live items on the graph.</p>
    {_kind_tiles(ontology, counts)}
    <h2 id="actions">Actions</h2>
    <p class="meta">Actions are verbs. Approved ones can write back to the tools you already run.</p>
    {_action_tiles(ontology)}
  </div>
</div>
"""
    return wrap(
        f"{name} catalog",
        body,
        nav="schema",
        pack_name=name,
        extra_script=_CATALOG_SCRIPT,
    )


_CATALOG_SCRIPT = """
<script>
(() => {
  const filter = document.getElementById("catalog-filter");
  const q = document.getElementById("q");
  if (q) q.dataset.local = "1";
  const nodes = [...document.querySelectorAll(".catalog-tree-node")];
  const links = [...document.querySelectorAll("[data-topic]")];
  const panels = [...document.querySelectorAll(".topic-panel")];
  const show = (id) => {
    if (!id) return;
    panels.forEach((panel) => panel.classList.toggle("on", panel.dataset.topic === id));
    document.querySelectorAll(".catalog-tree-link").forEach((link) => {
      link.classList.toggle("on", link.dataset.topic === id);
    });
  };
  const fromHash = () => (location.hash || "").replace("#topic-", "");
  const initial = fromHash() || (document.querySelector(".catalog-stage") || {}).dataset?.first;
  if (initial) show(initial);
  links.forEach((link) => {
    link.addEventListener("click", (ev) => {
      const id = link.dataset.topic;
      if (!id || !panels.length) return;
      ev.preventDefault();
      history.replaceState(null, "", "#topic-" + encodeURIComponent(id));
      show(id);
    });
  });
  window.addEventListener("hashchange", () => show(fromHash()));
  const applyFilter = (raw) => {
    const needle = String(raw || "").trim().toLowerCase();
    nodes.forEach((node) => {
      const hit = !needle || (node.dataset.name || "").includes(needle) || (node.dataset.id || "").includes(needle);
      node.hidden = needle ? !hit : false;
    });
    if (!needle) return;
    nodes.forEach((node) => {
      if (node.hidden) return;
      let parent = node.parentElement;
      while (parent) {
        const wrap = parent.closest(".catalog-tree-node");
        if (!wrap) break;
        wrap.hidden = false;
        parent = wrap.parentElement;
      }
    });
  };
  if (filter) {
    filter.addEventListener("input", () => applyFilter(filter.value));
  }
  if (q) {
    q.addEventListener("input", () => {
      if (filter) filter.value = q.value;
      applyFilter(q.value);
    });
    q.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") ev.preventDefault();
    });
  }
})();
</script>
"""
