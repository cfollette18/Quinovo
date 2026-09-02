"""Schema manager: look at types as YAML."""

from __future__ import annotations

import html

import yaml

from quinovo.language.models import Ontology


def schema_manager_html(ontology: Ontology) -> str:
    dumped = yaml.safe_dump(ontology.model_dump(by_alias=True), sort_keys=False)
    types = "".join(
        f"<li><code>{html.escape(item.api_name)}</code> — {html.escape(item.description)}</li>"
        for item in ontology.object_types
    )
    actions = "".join(
        f"<li><code>{html.escape(item.api_name)}</code> — {html.escape(item.description)}</li>"
        for item in ontology.action_types
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>Quinovo schema</title>
<style>
body {{ font-family: ui-sans-serif, system-ui; margin: 2rem; background:#111; color:#eee; }}
pre {{ background:#1c1c1c; padding:1rem; overflow:auto; }}
a {{ color:#d4a017; }}
</style></head><body>
<h1>{html.escape(ontology.ontology.display_name)}</h1>
<p>{html.escape(ontology.ontology.description)}</p>
<h2>Object types</h2><ul>{types}</ul>
<h2>Actions</h2><ul>{actions}</ul>
<h2>YAML</h2><pre>{html.escape(dumped)}</pre>
</body></html>"""
