"""Generated Object View. Human first, JSON behind a button."""

from __future__ import annotations

import json
from typing import Any

from quinovo.apps.chrome import empty_state, esc, workspace_tabs, wrap
from quinovo.apps.humanize import (
    confidence_label,
    fact_line,
    object_name,
    status_label,
    title_case,
)


def object_view_html(
    payload: dict[str, Any],
    actions: list[dict[str, Any]],
    links: dict[str, list[dict[str, Any]]] | None = None,
    series: dict[str, list[dict[str, Any]]] | None = None,
    pack_name: str = "",
) -> str:
    obj_type = str(payload.get("type", ""))
    obj_id = str(payload.get("id", ""))
    name = object_name(payload) or obj_id
    kind = title_case(obj_type)
    props = payload.get("properties") or {}
    rows = "".join(
        f"<tr><th>{esc(title_case(k))}</th><td>{esc(v)}</td></tr>"
        for k, v in props.items()
    )
    inferred = payload.get("facts") or []
    facts = "".join(
        "<li>"
        f"{esc(fact_line(item.get('predicate'), item.get('value')))} "
        f"<span class='pill pill-{esc(item.get('status'))}'>"
        f"{esc(status_label(str(item.get('status') or '')))}</span>"
        "</li>"
        for item in inferred
    )
    relevant = [
        action
        for action in actions
        if not action.get("parameters")
        or (action.get("parameters") or [{}])[0].get("object_type") in (None, obj_type)
    ]
    buttons = "".join(
        "<button type='button' class='btn btn-primary act' "
        f"data-action='{esc(action['api_name'])}' "
        f"data-param='{esc((action.get('parameters') or [{}])[0].get('api_name', ''))}'>"
        f"{esc(title_case(action['api_name']))}</button>"
        for action in relevant
    )
    predictions = payload.get("forecasts") or []
    forecast_bits = "".join(
        "<li>"
        f"{esc(title_case(item.get('metric')))}: {esc(item.get('point'))} "
        f"({esc(confidence_label(item.get('confidence')) or item.get('model'))})"
        "</li>"
        for item in predictions
    )
    link_bits = ""
    for side, neighbors in (links or {}).items():
        names = ", ".join(
            (
                f"<a href='/view/{esc(item.get('type'))}/{esc(item.get('id'))}'>"
                f"{esc(object_name(item) or item.get('id'))}</a>"
            )
            for item in neighbors
        )
        link_bits += f"<li>{esc(title_case(side))}: {names}</li>"
    chart_bits = ""
    for metric, points in (series or {}).items():
        values = ", ".join(esc(point.get("value")) for point in points)
        chart_bits += f"<li>{esc(title_case(metric))}: {values or 'none'}</li>"
    body = f"""
<div class="page-head">
  <p class="crumbs"><span>Catalog</span><span>{esc(kind)}</span><span class="here">{esc(name)}</span></p>
  <div class="page-head-row">
    <div>
      <h1>{esc(name)}</h1>
      <p class="meta">This is a {esc(kind.lower())}.</p>
    </div>
    <div class="page-actions">{buttons or ""}</div>
  </div>
  {workspace_tabs("graph")}
</div>
<div class="page">
  <div class="doc">
    <h2>About this</h2>
    <table class="kv">{rows or ""}</table>
    {"" if rows else empty_state("Nothing recorded yet", "Details show up here as this is filled in.", "/graph", "Back to the graph")}
    <h2>Connections</h2>
    <ul>{link_bits or "<li class='empty'>No connections yet.</li>"}</ul>
    <h2>What Quinovo noticed</h2>
    <ul class="facts">{facts or "<li class='empty'>Nothing extra yet.</li>"}</ul>
    <h2>Outlook</h2>
    <ul>{forecast_bits or "<li class='empty'>No outlook yet.</li>"}</ul>
    <h2>Over time</h2>
    <ul>{chart_bits or "<li class='empty'>No history yet.</li>"}</ul>
    <p id="action-note" role="status" aria-live="polite"></p>
  </div>
</div>
<script>
(() => {{
  const note = document.getElementById("action-note");
  document.querySelectorAll(".act").forEach((btn) => {{
    btn.addEventListener("click", async () => {{
      const param = btn.dataset.param;
      const body = {{
        actor: "human",
        parameters: param ? {{ [param]: {{ type: {json.dumps(obj_type)}, id: {json.dumps(obj_id)} }} }} : {{}},
      }};
      const res = await fetch("/actions/" + encodeURIComponent(btn.dataset.action), {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(body),
      }});
      const data = await res.json();
      if (!res.ok) {{
        note.className = "notice err";
        note.textContent = data.detail || res.status;
        return;
      }}
      location.reload();
    }});
  }});
}})();
</script>
"""
    return wrap(name, body, nav="graph", pack_name=pack_name)
