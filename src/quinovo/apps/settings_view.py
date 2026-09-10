"""Settings workspace: language model, API, and Hermes import."""

from __future__ import annotations

from quinovo.apps.chrome import esc, page_head, wrap
from quinovo.llm.engine import status_payload
from quinovo.llm.settings import LLMSettings


def settings_html(settings: LLMSettings, pack_name: str = "") -> str:
    public = status_payload(settings)
    ready = bool(public.get("ready"))
    tail = str(public.get("api_key_tail") or "")
    key_hint = f"Saved, last four {tail}" if public.get("api_key_set") else "Not saved yet"
    status_class = "ok" if ready else "warn"
    status_text = (
        f"Ready · {esc(settings.model)} is the language model Quinovo will use."
        if ready
        else "Add an API key, or import from Hermes, to turn the language model on."
    )
    source = "Hermes" if settings.source == "hermes" else "this page"
    checked = "checked" if settings.enabled else ""
    tracing = public.get("tracing") or {}
    if tracing.get("enabled"):
        trace_line = (
            "LLM calls are traced to Langfuse "
            f"({esc(tracing.get('environment') or 'development')}). "
            "When you turn down a proposal, that disagreement is saved so a specialist can train on it."
        )
    else:
        trace_line = "LLM tracing is off until Langfuse keys are set in .env."
    body = f"""
{page_head(
    "Settings",
    "Settings",
    "The language model notices patterns. You only approve what it is not sure about.",
    "settings",
)}
<div class="page">
  <div class="doc">
    <p class="status-banner {status_class}" role="status">{status_text}</p>
    <p class="story">Currently using values from {esc(source)}. The key stays on this machine and is never shown in full. {trace_line}</p>
    <form class="settings-form" method="post" action="/settings">
      <label class="field">
        <span>Provider</span>
        <input name="provider" value="{esc(settings.provider)}" placeholder="minimax" autocomplete="off"/>
      </label>
      <label class="field">
        <span>Model</span>
        <input name="model" value="{esc(settings.model)}" placeholder="MiniMax-M3" autocomplete="off"/>
      </label>
      <label class="field">
        <span>API URL</span>
        <input name="base_url" value="{esc(settings.base_url)}" placeholder="https://api.minimax.io/anthropic" autocomplete="off"/>
      </label>
      <label class="field">
        <span>API key</span>
        <input name="api_key" type="password" value="" placeholder="{esc(key_hint)}" autocomplete="off"/>
      </label>
      <label class="field">
        <span>Protocol</span>
        <select name="protocol">
          <option value="anthropic" {"selected" if settings.protocol == "anthropic" else ""}>Anthropic-compatible (MiniMax)</option>
          <option value="openai" {"selected" if settings.protocol == "openai" else ""}>OpenAI-compatible</option>
        </select>
      </label>
      <label class="check">
        <input type="checkbox" name="enabled" value="on" {checked}/>
        <span>Use this language model</span>
      </label>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Save changes</button>
        <button type="submit" class="btn btn-ghost" name="intent" value="import_hermes" formnovalidate>Import from Hermes</button>
        <button type="button" class="btn btn-ghost" id="test-llm">Test connection</button>
      </div>
    </form>
    <p id="note" role="status" aria-live="polite"></p>
  </div>
</div>
<script>
(() => {{
  const note = document.getElementById("note");
  const btn = document.getElementById("test-llm");
  if (!btn || !note) return;
  btn.addEventListener("click", async () => {{
    btn.disabled = true;
    note.className = "notice";
    note.textContent = "Checking the connection…";
    try {{
      const res = await fetch("/settings/test", {{ method: "POST" }});
      const data = await res.json().catch(() => ({{}}));
      if (!res.ok) {{
        note.className = "notice err";
        note.textContent = data.detail || "Could not reach the model.";
        return;
      }}
      note.className = "notice";
      note.textContent = data.message || "Connected.";
    }} catch (err) {{
      note.className = "notice err";
      note.textContent = String(err);
    }} finally {{
      btn.disabled = false;
    }}
  }});
}})();
</script>
"""
    return wrap("Settings", body, nav="settings", pack_name=pack_name)
