"""Train workspace: filter live data into sets for small specialist models."""

from __future__ import annotations

from typing import Any

from quinovo.apps.chrome import empty_state, esc, page_head, wrap
from quinovo.apps.humanize import title_case
from quinovo.language.models import Ontology

_SCRIPT = """
<script>
(() => {
  const note = document.getElementById("note");
  const list = document.getElementById("record-list");
  const empty = document.getElementById("record-empty");
  const form = document.getElementById("train-filters");
  const saveBtn = document.getElementById("save-set");
  const jobBtn = document.getElementById("start-job");
  const setName = document.getElementById("set-name");
  const jobName = document.getElementById("job-name");
  const sizeClass = document.getElementById("size-class");
  const saved = document.getElementById("saved-sets");
  const jobs = document.getElementById("job-list");
  const countEls = {
    things: document.getElementById("count-things"),
    connections: document.getElementById("count-connections"),
    noticed: document.getElementById("count-noticed"),
    changed: document.getElementById("count-changed"),
    total: document.getElementById("count-total"),
  };
  let lastDatasetId = "";

  function say(text, err) {
    if (!note) return;
    note.className = err ? "notice err" : "notice";
    note.textContent = text;
  }

  function filters() {
    const data = new FormData(form);
    const kinds = [...form.querySelectorAll("input[name=kinds]:checked")].map((el) => el.value);
    return {
      kinds: kinds.join(","),
      types: data.get("types") || "",
      status: data.get("status") || "all",
      q: data.get("q") || "",
      since: data.get("since") || "",
      until: data.get("until") || "",
      include_fields: data.get("include_fields") || "",
      exclude_fields: data.get("exclude_fields") || "",
      only_approved: data.get("only_approved") === "on" ? "1" : "",
    };
  }

  function card(record) {
    const art = document.createElement("article");
    art.className = "hitl-card";
    const pill = record.status === "needs_look" ? "pill-pending" : "pill-asserted";
    art.innerHTML =
      "<p class='kicker'>" + escapeHtml(record.family_label) + "</p>" +
      "<h3>" + escapeHtml(record.title) + "</h3>" +
      "<p>" + escapeHtml(record.summary) + "</p>" +
      "<p class='meta'><span class='pill " + pill + "'>" + escapeHtml(record.status_label) + "</span> " +
      escapeHtml(record.type_label || "") + "</p>";
    return art;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderRecords(payload) {
    if (!list) return;
    list.innerHTML = "";
    const records = payload.records || [];
    records.forEach((record) => list.appendChild(card(record)));
    if (empty) empty.hidden = records.length > 0;
    const counts = payload.counts || {};
    Object.keys(countEls).forEach((key) => {
      if (countEls[key]) countEls[key].textContent = String(counts[key] || 0);
    });
  }

  function tile(kind, title, meta, body) {
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML =
      "<p class='kicker'>" + escapeHtml(kind) + "</p>" +
      "<h3>" + escapeHtml(title) + "</h3>" +
      "<p>" + escapeHtml(body) + "</p>" +
      "<p class='meta'>" + escapeHtml(meta) + "</p>";
    return el;
  }

  async function refresh() {
    const query = new URLSearchParams(filters());
    const res = await fetch("/train/data?" + query.toString());
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      say(data.detail || "Could not load this set.", true);
      return;
    }
    renderRecords(data);
  }

  async function loadLists() {
    const [dsRes, jobRes] = await Promise.all([
      fetch("/train/datasets"),
      fetch("/train/jobs"),
    ]);
    const dsData = await dsRes.json().catch(() => ({ datasets: [] }));
    const jobData = await jobRes.json().catch(() => ({ jobs: [] }));
    if (saved) {
      saved.innerHTML = "";
      (dsData.datasets || []).forEach((row) => {
        const n = row.record_count || 0;
        const item = tile("Saved set", row.name, n + (n === 1 ? " item" : " items"), "Ready to teach a specialist.");
        item.dataset.id = row.id;
        item.addEventListener("click", () => {
          lastDatasetId = row.id;
          if (setName) setName.value = row.name;
          if (jobName && !jobName.value) jobName.value = row.name + " specialist";
          say("Using “" + row.name + "” for the next specialist.");
        });
        saved.appendChild(item);
      });
    }
    if (jobs) {
      jobs.innerHTML = "";
      (jobData.jobs || []).forEach((row) => {
        jobs.appendChild(tile(
          row.size_label || "Small specialist",
          row.name,
          (row.example_count || 0) + " examples · " + (row.status || ""),
          row.note || "Training file prepared."
        ));
      });
    }
  }

  if (form) {
    form.addEventListener("change", () => { refresh().catch((err) => say(String(err), true)); });
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      refresh().catch((err) => say(String(err), true));
    });
  }
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const name = (setName && setName.value.trim()) || "";
      if (!name) {
        say("Give this set a name first.", true);
        return;
      }
      const body = { name, filters: filters() };
      const res = await fetch("/train/datasets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        say(data.detail || "Could not save this set.", true);
        return;
      }
      lastDatasetId = data.id;
      say("Saved “" + data.name + "” · " + data.record_count + " items.");
      await loadLists();
    });
  }
  if (jobBtn) {
    jobBtn.addEventListener("click", async () => {
      if (!lastDatasetId) {
        say("Save a set first, or click one of the saved sets.", true);
        return;
      }
      const name = (jobName && jobName.value.trim()) || (setName && setName.value.trim()) || "Specialist";
      const res = await fetch("/train/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          dataset_id: lastDatasetId,
          size_class: (sizeClass && sizeClass.value) || "small",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        say(data.detail || "Could not start this specialist.", true);
        return;
      }
      say((data.size_label || "Small specialist") + " is ready: " + (data.note || "training file written."));
      await loadLists();
    });
  }
  loadLists().catch(() => {});
})();
</script>
"""


def _count_tiles(counts: dict[str, int]) -> str:
    tiles = (
        ("things", "Things", counts.get("things", 0)),
        ("connections", "Connections", counts.get("connections", 0)),
        ("noticed", "Noticed", counts.get("noticed", 0)),
        ("changed", "Changed", counts.get("changed", 0)),
    )
    bits = []
    for key, label, n in tiles:
        word = "item" if n == 1 else "items"
        bits.append(
            "<div class='tile'>"
            f"<p class='kicker'>{esc(label)}</p>"
            f"<h3 id='count-{key}'>{n}</h3>"
            f"<p class='meta'>{esc(word)}</p>"
            "</div>"
        )
    total = counts.get("total", 0)
    bits.append(
        "<div class='tile'>"
        "<p class='kicker'>In this set</p>"
        f"<h3 id='count-total'>{total}</h3>"
        f"<p class='meta'>{'item' if total == 1 else 'items'}</p>"
        "</div>"
    )
    return "".join(bits)


def _record_cards(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        pill = "pill-pending" if record.get("status") == "needs_look" else "pill-asserted"
        cards.append(
            "<article class='hitl-card'>"
            f"<p class='kicker'>{esc(record.get('family_label'))}</p>"
            f"<h3>{esc(record.get('title'))}</h3>"
            f"<p>{esc(record.get('summary'))}</p>"
            f"<p class='meta'><span class='pill {pill}'>{esc(record.get('status_label'))}</span> "
            f"{esc(record.get('type_label'))}</p>"
            "</article>"
        )
    return "".join(cards)


def _dataset_tiles(datasets: list[dict[str, Any]]) -> str:
    tiles = []
    for row in datasets:
        n = int(row.get("record_count") or 0)
        word = "item" if n == 1 else "items"
        tiles.append(
            "<div class='tile'>"
            "<p class='kicker'>Saved set</p>"
            f"<h3>{esc(row.get('name'))}</h3>"
            "<p>Ready to teach a specialist.</p>"
            f"<p class='meta'>{n} {word}</p>"
            "</div>"
        )
    return "".join(tiles)


def _job_tiles(jobs: list[dict[str, Any]]) -> str:
    tiles = []
    for row in jobs:
        n = int(row.get("example_count") or 0)
        tiles.append(
            "<div class='tile'>"
            f"<p class='kicker'>{esc(row.get('size_label') or 'Small specialist')}</p>"
            f"<h3>{esc(row.get('name'))}</h3>"
            f"<p>{esc(row.get('note') or 'Training file prepared.')}</p>"
            f"<p class='meta'>{n} examples · {esc(title_case(str(row.get('status') or '')))}</p>"
            "</div>"
        )
    return "".join(tiles)


def _kind_options(ontology: Ontology, selected: list[str]) -> str:
    bits = ['<option value="">Any kind</option>']
    for item in ontology.object_types:
        name = item.api_name
        mark = " selected" if name in selected else ""
        bits.append(f'<option value="{esc(name)}"{mark}>{esc(title_case(name))}</option>')
    for item in ontology.link_types:
        name = item.api_name
        mark = " selected" if name in selected else ""
        bits.append(f'<option value="{esc(name)}"{mark}>{esc(title_case(name))}</option>')
    return "".join(bits)


def _checked(families: list[str], family: str) -> str:
    return "checked" if family in families else ""


def train_html(
    ontology: Ontology,
    preview: dict[str, Any],
    datasets: list[dict[str, Any]] | None = None,
    jobs: list[dict[str, Any]] | None = None,
) -> str:
    name = ontology.ontology.display_name
    datasets = datasets or []
    jobs = jobs or []
    filters = preview.get("filters") or {}
    families = list(filters.get("kinds") or ["things", "connections", "noticed", "changed"])
    types = list(filters.get("types") or [])
    gate = str(filters.get("status") or "all")
    query = str(filters.get("q") or "")
    since = str(filters.get("since") or "")
    until = str(filters.get("until") or "")
    include = ",".join(filters.get("include_fields") or [])
    exclude = ",".join(filters.get("exclude_fields") or [])
    only_approved = "checked" if filters.get("only_approved") else ""
    records = preview.get("records") or []
    counts = preview.get("counts") or {}
    sel_all = "selected" if gate == "all" else ""
    sel_ok = "selected" if gate == "confirmed" else ""
    sel_look = "selected" if gate == "needs_look" else ""
    cards = _record_cards(records)
    empty_hidden = "hidden" if cards else ""
    saved = _dataset_tiles(datasets) or empty_state(
        "No saved sets yet",
        "Name this filter set and save it when the preview looks right.",
    )
    job_tiles = _job_tiles(jobs) or empty_state(
        "No specialists prepared yet",
        "Save a set first, then prepare a small specialist from it.",
    )
    body = f"""
{page_head(
    "Train",
    "Train",
    "Choose what this specialist should learn. Settings language models stay separate.",
    "train",
    actions=(
        '<button type="button" class="btn btn-ghost" id="save-set">Save this set</button>'
        '<button type="button" class="btn btn-primary" id="start-job">Prepare specialist</button>'
    ),
)}
<div class="page">
  <div class="doc">
    <p class="story">Pick the live things, connections, noticed facts, and changes this small specialist should study. You review the set in plain language. Quinovo writes a training file — it does not run a giant model. When you turn down a proposal on Inference, that disagreement is also saved to Langfuse so the agent can learn from it.</p>
    <form id="train-filters" class="train-filters" action="/train" method="get">
      <fieldset class="train-kinds">
        <legend>What to include</legend>
        <label class="check"><input type="checkbox" name="kinds" value="things" {_checked(families, "things")}/><span>Things</span></label>
        <label class="check"><input type="checkbox" name="kinds" value="connections" {_checked(families, "connections")}/><span>Connections</span></label>
        <label class="check"><input type="checkbox" name="kinds" value="noticed" {_checked(families, "noticed")}/><span>What Quinovo noticed</span></label>
        <label class="check"><input type="checkbox" name="kinds" value="changed" {_checked(families, "changed")}/><span>What changed</span></label>
      </fieldset>
      <div class="train-grid">
        <label class="field">
          <span>Kind of thing or connection</span>
          <select name="types">{_kind_options(ontology, types)}</select>
        </label>
        <label class="field">
          <span>How sure</span>
          <select name="status">
            <option value="all" {sel_all}>Include things still waiting for a look</option>
            <option value="confirmed" {sel_ok}>Only confirmed items</option>
            <option value="needs_look" {sel_look}>Only items that need a look</option>
          </select>
        </label>
        <label class="field">
          <span>Search</span>
          <input name="q" value="{esc(query)}" placeholder="Name or wording" autocomplete="off"/>
        </label>
        <label class="field">
          <span>From (date)</span>
          <input name="since" type="date" value="{esc(since)}"/>
        </label>
        <label class="field">
          <span>Until (date)</span>
          <input name="until" type="date" value="{esc(until)}"/>
        </label>
        <label class="field">
          <span>Keep only these details</span>
          <input name="include_fields" value="{esc(include)}" placeholder="name, status" autocomplete="off"/>
        </label>
        <label class="field">
          <span>Leave these details out</span>
          <input name="exclude_fields" value="{esc(exclude)}" placeholder="route_code" autocomplete="off"/>
        </label>
        <label class="field">
          <span>Set name</span>
          <input id="set-name" name="set_name" placeholder="Late packages" autocomplete="off"/>
        </label>
        <label class="field">
          <span>Specialist name</span>
          <input id="job-name" name="job_name" placeholder="Late-package specialist" autocomplete="off"/>
        </label>
        <label class="field">
          <span>Specialist size</span>
          <select id="size-class" name="size_class">
            <option value="tiny">Tiny specialist</option>
            <option value="small" selected>Small specialist</option>
            <option value="medium">Medium specialist</option>
          </select>
        </label>
      </div>
      <label class="check">
        <input type="checkbox" name="only_approved" {only_approved}/>
        <span>Only approved facts</span>
      </label>
      <div class="form-actions">
        <button type="submit" class="btn btn-secondary">Update preview</button>
      </div>
    </form>
    <p id="note" role="status" aria-live="polite"></p>
    <h2>This set</h2>
    <div class="tiles">{_count_tiles(counts)}</div>
    <h2>Review</h2>
    <div id="record-list">{cards}</div>
    <p id="record-empty" class="empty" {empty_hidden}>Nothing matches these choices yet. Widen the filters or add a connection.</p>
    <h2>Saved sets</h2>
    <div id="saved-sets" class="tiles">{saved}</div>
    <h2>Specialists</h2>
    <div id="job-list" class="tiles">{job_tiles}</div>
  </div>
</div>
{_SCRIPT}
"""
    return wrap("Train", body, nav="train", pack_name=name)
