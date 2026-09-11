"""Review queue: approve or reject. The loop runs itself."""

from __future__ import annotations

from typing import Any

from quinovo.apps.chrome import empty_state, esc, page_head, wrap
from quinovo.apps.humanize import (
    confidence_label,
    fact_line,
    kind_label,
    status_label,
    title_case,
)
from quinovo.language.models import Ontology


def _proposal_cards(proposals: list[dict[str, Any]]) -> str:
    if not proposals:
        return empty_state(
            "Nothing waiting",
            "Quinovo will ask when it is not sure.",
            "/chat",
            "Ask in chat",
        )
    cards = []
    for item in proposals:
        payload = item.get("payload") or {}
        kind = str(item.get("kind") or payload.get("kind") or "")
        title = item.get("title") or payload.get("api_name") or payload.get("action_type") or kind
        why = str(item.get("why") or "").strip()
        what = str(item.get("what") or "").strip()
        target = str(item.get("target") or "").strip()
        kicker = item.get("kicker") or kind_label(kind)
        sure = confidence_label(item.get("confidence"))
        why_html = (
            f"<p class='why-label'>Why now</p><p class='why'>{esc(why)}</p>" if why else ""
        )
        what_html = f"<p class='what'>{esc(what)}</p>" if what else ""
        target_html = f"<p class='target'>{esc(target)}</p>" if target else ""
        cards.append(
            "<article class='hitl-card'>"
            f"<p class='kicker'>{esc(str(kicker))}</p>"
            f"<h3>{esc(str(title))}</h3>"
            f"{why_html}{what_html}{target_html}"
            f"<p class='meta'>{esc(sure)}</p>"
            "<div class='hitl-actions'>"
            f"<button type='button' class='btn btn-primary' data-hitl='approve_proposal' data-id='{esc(item.get('id'))}'>Approve</button> "
            f"<button type='button' class='btn btn-ghost' data-hitl='reject_proposal' data-id='{esc(item.get('id'))}'>Turn down</button>"
            "</div>"
            "</article>"
        )
    return "".join(cards)


def _action_cards(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return ""
    cards = ["<h2>Actions waiting</h2>"]
    for item in actions:
        cards.append(
            "<article class='hitl-card'>"
            f"<p class='kicker'>Action</p>"
            f"<h3>{esc(title_case(str(item.get('action_type'))))}</h3>"
            f"<p>Asked by {esc(item.get('actor') or 'someone')}.</p>"
            "<div class='hitl-actions'>"
            f"<button type='button' class='btn btn-primary' data-hitl='approve_action' data-id='{esc(item.get('id'))}'>Approve</button> "
            f"<button type='button' class='btn btn-ghost' data-hitl='reject_action' data-id='{esc(item.get('id'))}'>Turn down</button>"
            "</div>"
            "</article>"
        )
    return "".join(cards)


def _fact_cards(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return empty_state(
            "Nothing extra noticed yet",
            "When Quinovo notices a pattern, it shows up here for a look.",
            "/settings",
            "Open Settings",
        )
    cards = []
    for fact in facts:
        obj_type = fact.get("object_type") or ""
        obj_id = fact.get("object_id") or ""
        status = str(fact.get("status") or "")
        approve = ""
        if status == "pending":
            approve = (
                f"<button type='button' class='btn btn-primary' "
                f"data-hitl='approve_fact' data-id='{esc(fact.get('id'))}'>Approve</button>"
            )
        href = f"/view/{esc(obj_type)}/{esc(obj_id)}" if obj_type and obj_id else "#"
        label = f"{title_case(str(obj_type))} {obj_id}".strip()
        sure = confidence_label(fact.get("confidence"))
        cards.append(
            "<article class='hitl-card'>"
            f"<p class='kicker'>{esc(status_label(status))}</p>"
            f"<h3><a href='{href}'>{esc(label)}</a></h3>"
            f"<p>{esc(fact_line(fact.get('predicate'), fact.get('value')))}</p>"
            f"<p class='meta'>{esc(sure)}</p>"
            f"<div class='hitl-actions'>{approve}</div>"
            "</article>"
        )
    return "".join(cards)


def inference_html(
    ontology: Ontology,
    facts: list[dict[str, Any]],
    proposals: list[dict[str, Any]] | None = None,
    pending_actions: list[dict[str, Any]] | None = None,
) -> str:
    name = ontology.ontology.display_name
    proposals = proposals or []
    pending_actions = pending_actions or []
    queued = len(proposals)
    heading = f"Needs a look · {queued} waiting" if queued else "Needs a look"
    body = f"""
{page_head(
    "Inference",
    "Inference",
    "The loop runs itself using the language model from Settings. You only approve or turn down what it is not sure about.",
    "logic",
)}
<div class="page">
  <h2 id="queue-heading">{esc(heading)}</h2>
  <div id="proposal-queue">{_proposal_cards(proposals)}</div>
  <div id="action-queue">{_action_cards(pending_actions)}</div>
  <h2>What Quinovo noticed</h2>
  <div id="fact-queue">{_fact_cards(facts)}</div>
  <p id="note" role="status" aria-live="polite"></p>
</div>
"""
    return wrap("Inference", body, nav="logic", pack_name=name, extra_script=_POLL_SCRIPT)


_POLL_SCRIPT = """
<script>
(() => {
  const heading = document.getElementById("queue-heading");
  const proposalsEl = document.getElementById("proposal-queue");
  const actionsEl = document.getElementById("action-queue");
  const factsEl = document.getElementById("fact-queue");
  let last = "";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
  const pretty = (s) => String(s || "").replace(/[_-]+/g, " ").replace(/\\b\\w/g, (c) => c.toUpperCase());
  const sure = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "";
    return Math.round(n <= 1 ? n * 100 : n) + "% sure";
  };
  function render(data) {
    const proposals = data.proposals || [];
    const actions = data.pending_actions || [];
    const facts = data.facts || [];
    if (heading) heading.textContent = proposals.length
      ? "Needs a look · " + proposals.length + " waiting"
      : "Needs a look";
    if (proposalsEl) {
      proposalsEl.innerHTML = proposals.length ? proposals.map((item) => {
        const payload = item.payload || {};
        const title = item.title || payload.api_name || payload.action_type || item.kind;
        const kicker = item.kicker || pretty(item.kind);
        const why = item.why || "";
        const what = item.what || "";
        const target = item.target || "";
        const whyHtml = why ? `<p class="why-label">Why now</p><p class="why">${esc(why)}</p>` : "";
        const whatHtml = what ? `<p class="what">${esc(what)}</p>` : "";
        const targetHtml = target ? `<p class="target">${esc(target)}</p>` : "";
        return `<article class="hitl-card"><p class="kicker">${esc(kicker)}</p><h3>${esc(title)}</h3>${whyHtml}${whatHtml}${targetHtml}<p class="meta">${esc(sure(item.confidence))}</p><div class="hitl-actions"><button type="button" class="btn btn-primary" data-hitl="approve_proposal" data-id="${esc(item.id)}">Approve</button> <button type="button" class="btn btn-ghost" data-hitl="reject_proposal" data-id="${esc(item.id)}">Turn down</button></div></article>`;
      }).join("") : "<p class='empty'>Nothing waiting. Quinovo will ask when it is not sure.</p>";
    }
    if (actionsEl) {
      actionsEl.innerHTML = actions.length ? ("<h2>Actions waiting</h2>" + actions.map((item) =>
        `<article class="hitl-card"><p class="kicker">Action</p><h3>${esc(pretty(item.action_type))}</h3><p>Asked by ${esc(item.actor || "someone")}.</p><div class="hitl-actions"><button type="button" class="btn btn-primary" data-hitl="approve_action" data-id="${esc(item.id)}">Approve</button> <button type="button" class="btn btn-ghost" data-hitl="reject_action" data-id="${esc(item.id)}">Turn down</button></div></article>`
      ).join("")) : "";
    }
    if (factsEl) {
      factsEl.innerHTML = facts.length ? facts.map((fact) => {
        const objType = fact.object_type || "";
        const objId = fact.object_id || "";
        const href = objType && objId ? "/view/" + encodeURIComponent(objType) + "/" + encodeURIComponent(objId) : "#";
        const approve = fact.status === "pending"
          ? `<button type="button" class="btn btn-primary" data-hitl="approve_fact" data-id="${esc(fact.id)}">Approve</button>`
          : "";
        return `<article class="hitl-card"><p class="kicker">${esc(pretty(fact.status))}</p><h3><a href="${esc(href)}">${esc(pretty(objType) + " " + objId)}</a></h3><p>${esc(pretty(fact.predicate))} — ${esc(fact.value)}</p><p class="meta">${esc(sure(fact.confidence))}</p><div class="hitl-actions">${approve}</div></article>`;
      }).join("") : "<p class='empty'>Nothing extra noticed yet.</p>";
    }
  }
  async function poll() {
    if (document.activeElement && document.activeElement.closest("[data-hitl]")) return;
    const data = await fetch("/inference.json").then((r) => r.json());
    const sig = JSON.stringify({
      p: (data.proposals || []).map((x) => x.id),
      a: (data.pending_actions || []).map((x) => x.id),
      f: (data.facts || []).map((x) => [x.id, x.status]),
    });
    if (sig === last) return;
    const first = last === "";
    last = sig;
    if (first) return;
    render(data);
  }
  poll().catch(() => {});
  setInterval(() => { poll().catch(() => {}); }, 4000);
})();
</script>
"""
