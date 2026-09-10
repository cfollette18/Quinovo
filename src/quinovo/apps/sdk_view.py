"""SDK page: the ontology, callable.

Quinovo's SDK is MCP plus the HTTP API — a typed surface an external app
calls to read objects, walk links, run actions, get facts. This page states
that story in human-first copy with the JSON contract behind a toggle.
"""

from __future__ import annotations

from typing import Any

from quinovo.apps.chrome import esc, workspace_tabs, wrap
from quinovo.apps.humanize import title_case


def sdk_html(contract: dict[str, Any], pack_name: str = "") -> str:
    mcp_tools = contract.get("mcp") or []
    tool_list = "".join(
        "<article class='tile'>"
        "<p class='kicker'>Tool</p>"
        f"<h3>{esc(title_case(str(item.get('name') or '')))}</h3>"
        f"<p>{esc(item.get('description') or '')}</p>"
        "</article>"
        for item in mcp_tools
    )
    body = f"""
<div class="page-head">
  <p class="crumbs"><span>Workspace</span><span class="here">SDK</span></p>
  <div class="page-head-row">
    <div>
      <h1>SDK</h1>
      <p class="meta">The ontology, callable. Quinovo's SDK is MCP plus the HTTP API — one typed surface to read objects, walk links, run actions, and get facts. No proprietary SDK to install; any MCP-compatible client is already a Quinovo client.</p>
    </div>
  </div>
  {workspace_tabs("sources")}
</div>
<div class="page">
  <div class="doc">
    <h2 id="mcp">MCP surface</h2>
    <p class="meta">Start Quinovo as an MCP server over stdio and point any client at it. Cursor, Claude Desktop, Hermes, or your own agent — all read and write the same ontology.</p>
    <div class="agent-cmd-wrap">
      <input class="agent-cmd" type="text" readonly
             value="uv run quinovo mcp --pack /abs/path/to/your/pack --db /abs/path/to/quinovo.sqlite"
             aria-label="Launch command"/>
      <button class="btn btn-ghost btn-copy" type="button" data-copy-cmd="sdk">Copy command</button>
    </div>
    <h3>Tools</h3>
    <div class="tiles">{tool_list or "<p class='empty'>No tools listed yet.</p>"}</div>
    <h2 id="http">HTTP API</h2>
    <p class="meta">The workspace is also an HTTP API. Read objects at <code>/objects/{'{type}'}</code>, walk links at <code>/objects/{'{type}'}/{'{id}'}/links/{'{side}'}</code>, apply actions at <code>/actions/{'{action_type}'}</code>, and pull sources at <code>/sources</code>. The full contract is available at <a href="/contract.json"><code>/contract.json</code></a> for power users — it is not rendered on this page.</p>
  </div>
</div>
"""
    copy_script = """
<script>
(() => {
  function flash(btn) {
    var orig = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(function () { btn.textContent = orig; }, 1500);
  }
  function copyText(text, btn) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { flash(btn); }, function () { flash(btn); });
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta); flash(btn);
    }
  }
  document.querySelectorAll(".btn-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var wrap = btn.closest(".agent-cmd-wrap");
      var input = wrap && wrap.querySelector(".agent-cmd");
      if (input) copyText(input.value, btn);
    });
  });
})();
</script>
"""
    return wrap("SDK", body, nav="sources", pack_name=pack_name,
                extra_script=copy_script)
