"""Connections page: data coming in, actions going out.

Human-first copy. No JSON on the page. Kind cards, then a short form.
"""

from __future__ import annotations

from typing import Any

from quinovo.apps.chrome import esc, workspace_tabs, wrap
from quinovo.apps.connections import (
    ACTION_KINDS,
    DATA_KINDS,
    icon_for,
    kind_by_id,
)
from quinovo.apps.humanize import (
    connection_kind_label,
    mask_secret,
    source_status_line,
    target_status_line,
    title_case,
)


def _options(names: list[str], selected: str = "") -> str:
    bits = []
    for name in names:
        on = " selected" if name == selected else ""
        bits.append(f'<option value="{esc(name)}"{on}>{esc(title_case(name))}</option>')
    return "".join(bits)


def _kind_card(item, layer: str, current: str) -> str:
    on = " on" if item.id == current else ""
    href = f"/sources?add={esc(item.id)}&layer={esc(layer)}"
    return (
        f'<a class="kind-card{on}" href="{href}">'
        f'<span class="kind-logo">{item.icon}</span>'
        f'<span class="kind-meta">'
        f'<span class="kind-name">{esc(item.name)}</span>'
        f'<span class="kind-blurb">{esc(item.blurb)}</span>'
        f"</span></a>"
    )


def _secret_hint(config: dict[str, Any]) -> str:
    token = config.get("token")
    if isinstance(token, str) and token:
        return f"Token saved, last four {esc(mask_secret(token)[-4:])}"
    headers = config.get("headers") or {}
    if isinstance(headers, dict):
        for value in headers.values():
            text = str(value)
            if text:
                tail = mask_secret(text)[-4:]
                return f"Access token saved, last four {esc(tail)}"
    password = config.get("smtp_password") or config.get("password")
    if isinstance(password, str) and password:
        return f"Password saved, last four {esc(mask_secret(password)[-4:])}"
    return ""


def _source_card(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "")
    kind = str(item.get("kind") or "")
    status = source_status_line(item)
    paused = not item.get("enabled", True)
    toggle_label = "Resume" if paused else "Pause"
    toggle_value = "on" if paused else "off"
    hint = _secret_hint(item.get("config") or {})
    hint_html = f'<p class="meta">{hint}</p>' if hint else ""
    feeds = title_case(str(item.get("object_type") or ""))
    auto = "Pulls on its own" if item.get("auto") else "Pulls when you ask"
    return (
        "<article class='conn-card'>"
        f'<span class="kind-logo">{icon_for(kind)}</span>'
        "<div class='conn-body'>"
        f"<h3>{esc(name)}</h3>"
        f"<p class='conn-status'>{esc(status)}</p>"
        f"<p class='meta'>Feeds {esc(feeds)} · {esc(auto)} · {esc(connection_kind_label(kind))}</p>"
        f"{hint_html}"
        "<div class='conn-actions'>"
        f"<form method='post' action='/sources/{esc(name)}/pull'>"
        "<button type='submit' class='btn btn-primary'>Pull now</button>"
        "</form>"
        f"<form method='post' action='/sources/{esc(name)}/enabled'>"
        f"<input type='hidden' name='enabled' value='{toggle_value}'/>"
        f"<button type='submit' class='btn btn-ghost'>{esc(toggle_label)}</button>"
        "</form>"
        f"<form method='post' action='/sources/{esc(name)}/delete'>"
        "<button type='submit' class='btn btn-ghost'>Remove</button>"
        "</form>"
        "</div></div></article>"
    )


def _target_card(item: dict[str, Any]) -> str:
    action = str(item.get("action_type") or "")
    kind = str(item.get("kind") or "")
    status = target_status_line(item)
    paused = not item.get("enabled", True)
    toggle_label = "Resume" if paused else "Pause"
    toggle_value = "on" if paused else "off"
    hint = _secret_hint(item.get("config") or {})
    hint_html = f'<p class="meta">{hint}</p>' if hint else ""
    return (
        "<article class='conn-card'>"
        f'<span class="kind-logo">{icon_for(kind)}</span>'
        "<div class='conn-body'>"
        f"<h3>{esc(title_case(action))}</h3>"
        f"<p class='conn-status'>{esc(status)}</p>"
        f"{hint_html}"
        "<div class='conn-actions'>"
        f"<form method='post' action='/action-targets/{esc(action)}/enabled'>"
        f"<input type='hidden' name='enabled' value='{toggle_value}'/>"
        f"<button type='submit' class='btn btn-ghost'>{esc(toggle_label)}</button>"
        "</form>"
        f"<form method='post' action='/action-targets/{esc(action)}/delete'>"
        "<button type='submit' class='btn btn-ghost'>Remove</button>"
        "</form>"
        "</div></div></article>"
    )


def _logic_card(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "")
    auto = "Runs on its own" if item.get("auto") else "Runs when you ask"
    return (
        "<article class='conn-card'>"
        f'<span class="kind-logo">{icon_for("http")}</span>'
        "<div class='conn-body'>"
        f"<h3>{esc(name)}</h3>"
        f"<p class='conn-status'>{esc(auto)}</p>"
        f"<p class='meta'>{esc(item.get('description') or '')}</p>"
        "<div class='conn-actions'>"
        f"<form method='post' action='/logic-sources/{esc(name)}/run'>"
        "<button type='submit' class='btn btn-primary'>Run now</button>"
        "</form>"
        "</div></div></article>"
    )


def _data_form(kind: str, object_types: list[str]) -> str:
    spec = kind_by_id(kind, "data")
    if spec is None:
        return ""
    extra = ""
    match kind:
        case "http" | "json":
            extra = """
      <label class="field"><span>Address</span>
        <input name="url" type="url" required placeholder="https://example.com/things"/></label>
      <label class="field"><span>List path</span>
        <input name="rows_path" placeholder="data.items — leave blank if the page is already a list"/></label>
      <label class="field"><span>Access token</span>
        <input name="token" type="password" autocomplete="off" placeholder="optional"/></label>
            """
        case "csv":
            extra = """
      <label class="field"><span>File path</span>
        <input name="path" required placeholder="/home/you/inbox.csv"/></label>
            """
        case "webhook":
            extra = """
      <label class="field"><span>Shared token</span>
        <input name="token" type="password" autocomplete="off" placeholder="optional — callers send this as a bearer token"/></label>
      <p class="meta">After you save, other systems POST to <span class="mono">/ingest/your-name</span>.</p>
            """
        case "sql":
            extra = """
      <label class="field"><span>Database</span>
        <input name="dsn" required placeholder="path/to/file.sqlite or a postgres URL"/></label>
      <label class="field"><span>Query</span>
        <input name="query" required placeholder="select id, status from packages"/></label>
            """
        case "mcp":
            extra = """
      <label class="field"><span>MCP address</span>
        <input name="url" placeholder="https://example.com/mcp — or leave blank to use a local command"/></label>
      <label class="field"><span>Local command</span>
        <input name="command" placeholder="optional — one-shot stdio JSON-RPC"/></label>
      <label class="field"><span>Tool name</span>
        <input name="tool" required placeholder="list_things"/></label>
      <label class="field"><span>Access token</span>
        <input name="token" type="password" autocomplete="off" placeholder="optional"/></label>
            """
        case _:
            extra = ""
    return f"""
    <form class="conn-form" method="post" action="/sources/form">
      <input type="hidden" name="kind" value="{esc(kind)}"/>
      <p class="story">Connecting {esc(spec.name)}. Name it, say which kind of thing it fills, then the address.</p>
      <label class="field"><span>Name</span>
        <input name="name" required placeholder="warehouse feed"/></label>
      <label class="field"><span>These become</span>
        <select name="object_type" required>{_options(object_types)}</select></label>
      {extra}
      <label class="field"><span>Id field</span>
        <input name="id_field" placeholder="tracking_id — if that is how the other system names the id"/></label>
      <label class="field"><span>Field map</span>
        <textarea name="property_map" rows="3" placeholder="tracking_id → id&#10;state → status"></textarea></label>
      <label class="check">
        <input type="checkbox" name="auto" value="on"/>
        <span>Pull this on every loop</span>
      </label>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Save connection</button>
        <a class="btn btn-ghost" href="/sources">Cancel</a>
      </div>
    </form>
    """


def _action_form(kind: str, action_types: list[str]) -> str:
    spec = kind_by_id(kind, "action")
    if spec is None:
        return ""
    extra = ""
    match kind:
        case "webhook" | "http":
            extra = """
      <label class="field"><span>Address</span>
        <input name="url" type="url" required placeholder="https://example.com/hook"/></label>
      <label class="field"><span>Access token</span>
        <input name="token" type="password" autocomplete="off" placeholder="optional"/></label>
            """
        case "slack":
            extra = """
      <label class="field"><span>Slack incoming webhook</span>
        <input name="url" type="url" required placeholder="https://hooks.slack.com/services/…"/></label>
            """
        case "email":
            extra = """
      <label class="field"><span>Send to</span>
        <input name="to" type="email" required placeholder="ops@example.com"/></label>
      <label class="field"><span>Mail server</span>
        <input name="smtp_host" placeholder="leave blank to log the message instead"/></label>
      <label class="field"><span>Mail user</span>
        <input name="smtp_user" autocomplete="off"/></label>
      <label class="field"><span>Mail password</span>
        <input name="smtp_password" type="password" autocomplete="off"/></label>
            """
        case "mcp":
            extra = """
      <label class="field"><span>MCP address</span>
        <input name="url" type="url" required placeholder="https://example.com/mcp"/></label>
      <label class="field"><span>Tool name</span>
        <input name="tool" required placeholder="apply_change"/></label>
      <label class="field"><span>Access token</span>
        <input name="token" type="password" autocomplete="off" placeholder="optional"/></label>
            """
        case "sql":
            extra = """
      <label class="field"><span>Database</span>
        <input name="dsn" required placeholder="path/to/file.sqlite"/></label>
      <label class="field"><span>Statement</span>
        <input name="statement" required placeholder="INSERT INTO outbound (action_type) VALUES (:action_type)"/></label>
      <label class="field"><span>Allowed tables</span>
        <input name="allowed_tables" required placeholder="outbound"/></label>
      <p class="meta">Only INSERT or UPDATE, and only on the tables you list. Every send is audited.</p>
            """
        case _:
            extra = ""
    return f"""
    <form class="conn-form" method="post" action="/action-targets/form">
      <input type="hidden" name="kind" value="{esc(kind)}"/>
      <p class="story">When this action is applied, Quinovo will {esc(spec.blurb.lower())}</p>
      <label class="field"><span>Action</span>
        <select name="action_type" required>{_options(action_types)}</select></label>
      {extra}
      <label class="field"><span>Note</span>
        <input name="description" placeholder="optional — for you"/></label>
      <div class="form-actions">
        <button type="submit" class="btn btn-primary">Save write-back</button>
        <a class="btn btn-ghost" href="/sources">Cancel</a>
      </div>
    </form>
    """


def _empty_data() -> str:
    return (
        "<p class='empty invite'>Nothing is flowing in yet. Pick a kind above "
        "and connect the first system — Quinovo will turn its rows into objects.</p>"
    )


def _empty_actions() -> str:
    return (
        "<p class='empty invite'>No write-backs yet. Pick where an applied action "
        "should land — Slack, mail, a webhook, another MCP server, or a gated database write.</p>"
    )


def sources_html(
    sources: list[dict[str, Any]],
    logic_sources: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    pack_name: str = "",
    *,
    add: str = "",
    layer: str = "data",
    object_types: list[str] | None = None,
    action_types: list[str] | None = None,
) -> str:
    del runs
    object_types = object_types or []
    action_types = action_types or []
    add_kind = add if add else ""
    add_layer = layer if layer in {"data", "action"} else "data"
    data_picker = "".join(_kind_card(item, "data", add_kind if add_layer == "data" else "") for item in DATA_KINDS)
    action_picker = "".join(_kind_card(item, "action", add_kind if add_layer == "action" else "") for item in ACTION_KINDS)
    data_cards = "".join(_source_card(item) for item in sources) or _empty_data()
    action_cards = "".join(_target_card(item) for item in targets) or _empty_actions()
    form = ""
    if add_kind and add_layer == "data":
        form = _data_form(add_kind, object_types)
    elif add_kind and add_layer == "action":
        form = _action_form(add_kind, action_types)
    logic_block = ""
    if logic_sources:
        logic_cards = "".join(_logic_card(item) for item in logic_sources)
        logic_block = f"""
    <h2>Logic from elsewhere</h2>
    <p class="meta">A function that produces facts can live outside Quinovo. These still run here.</p>
    <div class="conn-list">{logic_cards}</div>
        """
    body = f"""
<div class="page-head">
  <p class="crumbs"><span>Workspace</span><span class="here">Sources</span></p>
  <div class="page-head-row">
    <div>
      <h1>Sources</h1>
      <p class="meta">Connect any system with a small set of adapters — a web address, a file, a push, a database, or MCP. There is no marketplace of hundreds of connectors. MCP is the connector.</p>
    </div>
  </div>
  {workspace_tabs("sources")}
</div>
<div class="page">
  <div class="doc conn-page">
    <div class="conn-layers">
      <section class="conn-layer" id="sources">
        <h2>Data coming in</h2>
        <p class="meta">Other systems send things here. Quinovo keeps the objects.</p>
        <div class="kind-grid" aria-label="Add a data connection">{data_picker}</div>
        {form if add_layer == "data" else ""}
        <div class="conn-list">{data_cards}</div>
      </section>
      <section class="conn-layer" id="targets">
        <h2>Actions going out</h2>
        <p class="meta">When you approve an action, Quinovo can tell another system. A failed send is logged and never undoes the local change.</p>
        <div class="kind-grid" aria-label="Add a write-back">{action_picker}</div>
        {form if add_layer == "action" else ""}
        <div class="conn-list">{action_cards}</div>
      </section>
    </div>
    {logic_block}
  </div>
</div>
"""
    return wrap("Sources", body, nav="sources", pack_name=pack_name)
