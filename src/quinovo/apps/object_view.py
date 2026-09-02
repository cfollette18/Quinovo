"""Generated Object View. The button is the action. Not Workshop."""

from __future__ import annotations

import html
from typing import Any


def object_view_html(
    payload: dict[str, Any],
    actions: list[dict[str, Any]],
    links: dict[str, list[dict[str, Any]]] | None = None,
    series: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    title = html.escape(f"{payload.get('type', '')} {payload.get('id', '')}")
    props = payload.get("properties") or {}
    rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in props.items()
    )
    inferred = payload.get("inferred") or []
    facts = "".join(
        f"<li>{html.escape(str(item.get('predicate')))} = {html.escape(str(item.get('value')))} "
        f"({html.escape(str(item.get('status')))})</li>"
        for item in inferred
    )
    buttons = "".join(
        f"<form method='post' action='/actions/{html.escape(action['api_name'])}'>"
        f"<input type='hidden' name='id' value='{html.escape(str(payload.get('id', '')))}'/>"
        f"<button type='submit'>{html.escape(action['api_name'])}</button></form>"
        for action in actions
    )
    predictions = payload.get("predictions") or []
    forecast_bits = "".join(
        f"<li>{html.escape(str(item.get('metric')))}={html.escape(str(item.get('point')))} "
        f"via {html.escape(str(item.get('model')))}</li>"
        for item in predictions
    )
    link_bits = ""
    for side, neighbors in (links or {}).items():
        names = ", ".join(
            html.escape(str(item.get("properties", {}).get("name") or item.get("id")))
            for item in neighbors
        )
        link_bits += f"<li>{html.escape(side)}: {names}</li>"
    chart_bits = ""
    for metric, points in (series or {}).items():
        values = ", ".join(html.escape(str(point.get("value"))) for point in points)
        chart_bits += f"<li>{html.escape(metric)}: {values or 'none'}</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>{title}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui; margin: 2rem; background:#111; color:#eee; }}
th {{ text-align:left; padding-right:1rem; color:#aaa; }}
button {{ margin-right:.5rem; padding:.4rem .8rem; }}
a {{ color:#d4a017; }}
</style></head><body>
<p><a href="/manager">Schema manager</a></p>
<h1>{title}</h1>
<table>{rows}</table>
<h2>Links</h2><ul>{link_bits or "<li>none</li>"}</ul>
<h2>Inferred</h2><ul>{facts or "<li>none</li>"}</ul>
<h2>Predictions</h2><ul>{forecast_bits or "<li>none</li>"}</ul>
<h2>Series</h2><ul>{chart_bits or "<li>none</li>"}</ul>
<h2>Actions</h2>{buttons or "<p>none</p>"}
</body></html>"""
