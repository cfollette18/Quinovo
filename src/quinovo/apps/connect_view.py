"""Sign-in and guided connect-agent pages for the local Quinovo instance.

These are the friendly path behind the "Connect your agent" button on the
landing page. The page shows agent logo cards (Cursor, Claude, Hermes,
generic MCP). No raw JSON is rendered. The launch command is a single line in
a styled input box; the full config a power user needs is fetched from
``/connect/config/{agent}`` on copy and put on the clipboard — never shown as
a JSON block on the page.

Sign-in model: local, single-user, honest. The first visitor sets a
passphrase (stored under ``.data/``); later visitors must enter it. A signed
cookie proves the caller has claimed this instance. See
:mod:`quinovo.apps.session`.
"""

from __future__ import annotations

import html
import platform
from pathlib import Path

from quinovo.apps.agents import AGENTS, launch_command, logo_svg
from quinovo.apps.landing import BRICKS, GITHUB_URL

__all__ = ["config_text", "connect_html", "signin_html"]


def _shell() -> str:
    """Canonical Quinovo launch command for the config snippet.

    We always use ``uv run quinovo`` (the same form the landing page shows and
    the same form the user runs to start the server) so the guided snippet is
    portable and not tied to a specific venv's absolute path. The absolute
    paths that matter — the pack and the database — are filled in separately.
    """
    return "uv run quinovo"


def _cursor_config(pack: str, db: str) -> str:
    cmd = _shell()
    if cmd == "uv run quinovo":
        cmd_line = '"command": "uv",\n  "args": ["run", "quinovo", "mcp",'
        args_tail = (
            f'\n             "--pack", "{pack}",'
            f'\n             "--db",   "{db}"]'
        )
    else:
        cmd_line = f'"command": "{cmd}",\n  "args": ["mcp",'
        args_tail = (
            f'\n         "--pack", "{pack}",'
            f'\n         "--db",   "{db}"]'
        )
    return (
        '{\n'
        '  "mcpServers": {\n'
        '    "quinovo": {\n'
        f'  {cmd_line}{args_tail}\n'
        '    }\n'
        '  }\n'
        '}'
    )


def _claude_config(pack: str, db: str) -> str:
    # Claude Desktop uses the same JSON shape as Cursor.
    return _cursor_config(pack, db)


def _hermes_config(pack: str, db: str) -> str:
    cmd = _shell()
    if cmd == "uv run quinovo":
        return (
            'mcp_servers:\n'
            '  quinovo:\n'
            '    command: uv\n'
            '    args:\n'
            '      - run\n'
            '      - quinovo\n'
            '      - mcp\n'
            '      - --pack\n'
            f'      - {pack}\n'
            '      - --db\n'
            f'      - {db}\n'
            '    connect_timeout: 30\n'
            '    trust: full'
        )
    return (
        'mcp_servers:\n'
        '  quinovo:\n'
        f'    command: {cmd}\n'
        '    args:\n'
        '      - mcp\n'
        '      - --pack\n'
        f'      - {pack}\n'
        '      - --db\n'
        f'      - {db}\n'
        '    connect_timeout: 30\n'
        '    trust: full'
    )


def config_text(agent_id: str, pack: str, db: str) -> str:
    """Full config block for an agent, returned as plain text (never rendered).

    Used by the ``/connect/config/{agent}`` endpoint so the copy button can put
    the real JSON/YAML on the clipboard without showing raw config on the page.
    """
    if agent_id == "cursor":
        return _cursor_config(pack, db)
    if agent_id == "claude":
        return _claude_config(pack, db)
    if agent_id == "hermes":
        return _hermes_config(pack, db)
    # generic / other: the single-line shell command
    return launch_command(pack, db)


def _claude_config_path() -> str:
    system = platform.system()
    if system == "Darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    if system == "Windows":
        return "%APPDATA%\\Claude\\claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"


def _agent_where(agent_id: str) -> str:
    if agent_id == "claude":
        return _claude_config_path()
    for a in AGENTS:
        if a.id == agent_id:
            return a.where
    return "Your client's MCP config"


def _agent_card(agent, pack: str, db: str) -> str:
    cmd = launch_command(pack, db)
    where = _agent_where(agent.id)
    return f"""
        <details class="agent-card" data-agent="{agent.id}">
          <summary class="agent-card-head">
            <span class="agent-logo">{logo_svg(agent.id)}</span>
            <span class="agent-card-meta">
              <span class="agent-card-name">{agent.name}</span>
              <span class="agent-card-blurb">{agent.blurb}</span>
            </span>
            <span class="agent-card-chev" aria-hidden="true">▸</span>
          </summary>
          <div class="agent-card-body">
            <p class="agent-where"><span class="agent-where-label">Config file:</span>
              <code class="agent-where-path">{html.escape(where)}</code></p>
            <p class="agent-steps">{agent.steps}</p>
            <div class="agent-cmd-wrap">
              <input class="agent-cmd" type="text" readonly value="{html.escape(cmd)}"
                     aria-label="Launch command for {agent.name}"/>
              <button class="btn btn-ghost btn-copy" type="button"
                      data-copy-cmd="{agent.id}" data-agent-id="{agent.id}">Copy config</button>
            </div>
          </div>
        </details>"""


def _nav_cta(signed_in: bool) -> str:
    if signed_in:
        return (
            '<a class="site-cta" href="/signout" '
            'onclick="fetch(\'/signout\',{method:\'POST\',redirect:\'manual\'})'
            '.then(()=>location=\'/\').catch(()=>location=\'/\');return false;">'
            'Sign out</a>'
        )
    return '<a class="site-cta" href="/signin">Sign in</a>'


def _page_shell(title: str, body: str, signed_in: bool) -> str:
    nav = _nav_cta(signed_in)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)} — Quinovo</title>
  <meta name="theme-color" content="#f9f7f4"/>
  <meta name="description" content="Connect an MCP-compatible agent to this local Quinovo instance."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,700;1,9..40,400&family=DM+Mono:wght@400;500&display=swap"/>
  <link rel="stylesheet" href="/assets/landing.css"/>
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"/>
  <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"/>
  <link rel="icon" href="/assets/favicon-32.png" sizes="32x32" type="image/png"/>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site">
    <div class="site-inner">
      <a class="brand" href="/">{BRICKS}<span class="brand-name">quinovo</span></a>
      <nav class="site-nav" aria-label="Landing">
        <a href="/#why">Why</a>
        <a href="/#how">How it works</a>
        <a href="/#actions">Actions</a>
        <a href="/#connect">Connect</a>
        <a href="/twin">Workspace</a>
        {nav}
      </nav>
    </div>
  </header>
  <main id="main">
{body}
  </main>
  <footer class="site-foot">
    <div class="foot-inner">
      <div class="foot-brand">
        <a class="brand" href="/">{BRICKS}<span class="brand-name">quinovo</span></a>
        <p class="foot-tag">Operational ontology kernel. Apache-2.0.</p>
      </div>
      <nav class="foot-nav">
        <a href="{GITHUB_URL}" rel="noopener">GitHub</a>
        <a href="/twin">Workspace</a>
        <a href="/settings">Settings</a>
      </nav>
      <p class="foot-credit">built by <a href="{GITHUB_URL}" rel="noopener">cfollette18</a></p>
    </div>
  </footer>
</body>
</html>"""


def signin_html(next_path: str = "/connect", error: str | None = None,
                 first_visit: bool = False) -> str:
    """Render the local sign-in page.

    ``first_visit`` is True when no passphrase has been set yet — the form
    then asks the user to *create* a passphrase and immediately signs them in.
    """
    heading = "Claim this Quinovo" if first_visit else "Sign in to Quinovo"
    sub = (
        "This is a local, single-user tool. Set a passphrase to claim this "
        "instance — you'll use it on later visits. It never leaves this machine."
        if first_visit
        else "Enter the passphrase you set when you first claimed this Quinovo instance."
    )
    label = "Set a passphrase" if first_visit else "Passphrase"
    button = "Claim and continue" if first_visit else "Sign in"
    error_html = (
        f'<p class="form-error" id="auth-error" role="alert">{html.escape(error)}</p>'
        if error else ""
    )
    invalid = ' aria-invalid="true" aria-describedby="auth-error"' if error else ""

    body = f"""    <section class="auth">
      <div class="auth-card">
        <p class="kicker">Local sign-in</p>
        <h1>{heading}</h1>
        <p class="auth-sub">{sub}</p>
        <form class="auth-form" method="post" action="/signin">
          <input type="hidden" name="next" value="{html.escape(next_path)}"/>
          <label class="field">
            <span class="field-label">{label}</span>
            <input class="field-input" type="password" name="passphrase"
                   autocomplete="current-password" autofocus required
                   minlength="4" placeholder="at least 4 characters"{invalid}/>
          </label>
          {error_html}
          <button class="btn btn-primary" type="submit">{button}</button>
        </form>
        <p class="auth-note">
          No accounts, no email, no OAuth. The passphrase is stored only on this
          machine under <code>.data/</code> (gitignored). The LLM API key is
          separate and lives in <a href="/settings">Settings</a>.
        </p>
        <p class="auth-back"><a href="/#connect">&larr; back to the landing page</a></p>
      </div>
    </section>"""
    return _page_shell("Sign in", body, signed_in=False)


def connect_html(pack_path: Path, db_path: Path, signed_in: bool = True) -> str:
    """Render the guided connect-an-agent page (requires a session)."""
    pack = str(pack_path.resolve())
    db = str(db_path.resolve())
    cards_html = "".join(_agent_card(a, pack, db) for a in AGENTS)

    body = f"""    <section class="connect-guide">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">Connect your agent</p>
          <h1>Point your agent at Quinovo.</h1>
          <p class="section-sub">
            Quinovo is an MCP server over stdio. Pick your agent below, copy the
            launch command into the file it shows you, restart the agent, and
            you're in. The paths below are already filled in for this install —
            no guessing. Need the full JSON/YAML block? The Copy config button
            puts it on your clipboard without showing raw config on the page.
          </p>
        </header>

        <div class="agent-meta">
          <div class="meta-row"><span class="meta-label">Pack (the world):</span>
            <code class="meta-value">{html.escape(pack)}</code></div>
          <div class="meta-row"><span class="meta-label">Database (facts):</span>
            <code class="meta-value">{html.escape(db)}</code></div>
        </div>

        <div class="agent-cards" id="agent-cards">
{cards_html}
        </div>

        <div class="connect-test">
          <div class="connect-test-head">
            <h3>Not sure it's reachable?</h3>
            <p>Quinovo's HTTP server is what your agent's MCP server talks to
            behind the scenes. Ping it to confirm it's up.</p>
          </div>
          <button class="btn btn-ghost" id="test-conn" type="button">Test connection</button>
          <p class="test-result" id="test-result" aria-live="polite"></p>
        </div>

        <div class="connect-cta">
          <p>Once your agent sees Quinovo, ask it to read the ontology, propose
          types, or run an action. Then come back to the
          <a href="/twin">workspace</a> to approve what it proposes.</p>
          <div class="hero-cta">
            <a class="btn btn-primary" href="/twin">Open the workspace</a>
            <a class="btn btn-ghost" href="/#connect">Back to landing</a>
          </div>
        </div>
      </div>
    </section>

    <script>
      (function() {{
        function flash(btn) {{
          var orig = btn.textContent;
          btn.textContent = "Copied!";
          setTimeout(function () {{ btn.textContent = orig; }}, 1500);
        }}
        function copyText(text, btn) {{
          if (navigator.clipboard && navigator.clipboard.writeText) {{
            navigator.clipboard.writeText(text).then(function () {{ flash(btn); }}, function () {{ flash(btn); }});
          }} else {{
            var ta = document.createElement("textarea");
            ta.value = text; document.body.appendChild(ta); ta.select();
            try {{ document.execCommand("copy"); }} catch (e) {{}}
            document.body.removeChild(ta); flash(btn);
          }}
        }}

        document.querySelectorAll(".btn-copy").forEach(function (btn) {{
          btn.addEventListener("click", function () {{
            var card = btn.closest(".agent-card");
            var input = card && card.querySelector(".agent-cmd");
            var agentId = btn.getAttribute("data-agent-id");
            if (!input || !agentId) return;
            // Copy the single-line launch command from the visible input box.
            copyText(input.value, btn);
            // Also fetch the full JSON/YAML config for this agent and put it on
            // the clipboard so a power user has the real block — without ever
            // rendering raw JSON on the page.
            fetch("/connect/config/" + encodeURIComponent(agentId))
              .then(function (r) {{ if (!r.ok) return ""; return r.text(); }})
              .then(function (cfg) {{
                if (cfg && navigator.clipboard && navigator.clipboard.writeText) {{
                  navigator.clipboard.writeText(cfg).catch(function () {{}});
                }}
              }})
              .catch(function () {{}});
          }});
        }});

        var testBtn = document.getElementById("test-conn");
        var testResult = document.getElementById("test-result");
        if (testBtn) {{
          testBtn.addEventListener("click", function() {{
            testResult.textContent = "Pinging /healthz…";
            fetch("/connect/test", {{method: "POST"}})
              .then(function(r) {{ return r.json(); }})
              .then(function(j) {{
                var ok = j && j.ok;
                testResult.textContent = ok
                  ? "Reachable — Quinovo is up and serving the ontology."
                  : "Could not confirm Quinovo is reachable.";
              }})
              .catch(function(e) {{
                testResult.textContent = "Could not reach Quinovo: " + e;
              }});
          }});
        }}
      }})();
    </script>"""
    return _page_shell("Connect your agent", body, signed_in=signed_in)
