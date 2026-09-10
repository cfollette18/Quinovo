"""Audit workspace: what changed, in plain language."""

from __future__ import annotations

from typing import Any

from quinovo.apps.chrome import empty_state, esc, page_head, wrap
from quinovo.apps.humanize import actor_label, title_case
from quinovo.language.models import Ontology


def audit_html(ontology: Ontology, entries: list[Any]) -> str:
    name = ontology.ontology.display_name
    cards = []
    for row in reversed(list(entries)):
        params = row.parameters if hasattr(row, "parameters") else {}
        detail_bits = []
        if params:
            for key, value in params.items():
                detail_bits.append(f"{esc(title_case(str(key)))}: {esc(value)}")
        detail_line = " · ".join(detail_bits)
        cards.append(
            "<article class='hitl-card'>"
            f"<p class='kicker'>{esc(row.created_at)}</p>"
            f"<h3>{esc(title_case(row.action_type))}</h3>"
            f"<p>By {esc(actor_label(row.actor))} · {esc(title_case(str(row.result)))}</p>"
            + (f"<p class='meta'>{detail_line}</p>" if detail_line else "")
            + "</article>"
        )
    empty = empty_state(
        "Nothing has changed yet",
        "Once Quinovo or you approve a proposal, run an action, or turn something down, it shows up here.",
        "/inference",
        "Open Inference",
    )
    body = f"""
{page_head("Audit", "Audit", "A record of every change. Nothing is edited in place.", "audit")}
<div class="page">
  {"".join(cards) or empty}
</div>
"""
    return wrap("Audit", body, nav="audit", pack_name=name)
