"""Public landing page for Quinovo.

Standalone HTML: split hero with a Graph workspace mockup, a navy how-it-works
band with an architecture diagram, why-cards with product graphics, an Action
write-back grid, and MCP agent logo cards. No raw JSON is ever rendered.
"""

from __future__ import annotations

from quinovo.apps.action_grid import action_section_html
from quinovo.apps.agents import AGENTS, launch_command, logo_svg
from quinovo.apps.landing_graphics import (
    BRICKS,
    BRICKS_ON_DARK,
    arch_diagram,
    hero_workspace_mockup,
    primitive_graphic,
    why_graphic,
)

GITHUB_URL = "https://github.com/cfollette18/Quinovo"

PACK_PLACEHOLDER = "/abs/path/to/your/pack"
DB_PLACEHOLDER = "/abs/path/to/quinovo.sqlite"


def _agent_card(agent, cmd: str) -> str:
    """One agent logo card. Collapsed = logo + name + blurb.

    Expanded = plain-language steps + a single-line launch command in a styled
    input box + a copy button. No JSON block anywhere.
    """
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
            <code class="agent-where-path">{agent.where}</code></p>
          <p class="agent-steps">{agent.steps}</p>
          <div class="agent-cmd-wrap">
            <input class="agent-cmd" type="text" readonly value="{cmd}"
                   aria-label="Launch command for {agent.name}"/>
            <button class="btn btn-ghost btn-copy" type="button"
                    data-copy-cmd="{agent.id}">Copy command</button>
          </div>
        </div>
      </details>"""


def _agent_cards_html() -> str:
    cmd = launch_command(PACK_PLACEHOLDER, DB_PLACEHOLDER)
    return "".join(_agent_card(a, cmd) for a in AGENTS)


def landing_html(signed_in: bool = False) -> str:
    if signed_in:
        connect_href = "/connect"
        connect_label = "Manage connection"
        hero_primary_href = "/twin"
        hero_primary_label = "Open the workspace"
        hero_secondary_href = "/connect"
        hero_secondary_label = "Manage connection"
        nav_cta_href = "/twin"
        nav_cta_label = "Open the workspace"
        connect_sub = (
            "You're signed in. Open the guided flow to connect another agent, "
            "copy a config with the paths filled in, or test the connection."
        )
    else:
        connect_href = "/signin?next=/connect"
        connect_label = "Connect your agent"
        hero_primary_href = connect_href
        hero_primary_label = "Connect your agent"
        hero_secondary_href = "#how"
        hero_secondary_label = "See how it works"
        nav_cta_href = connect_href
        nav_cta_label = "Connect your agent"
        connect_sub = (
            "This is a local, single-user tool. The button signs you in first "
            "(you set a passphrase on your first visit), then walks you through "
            "the connect steps with the paths already filled in."
        )

    agent_cards = _agent_cards_html()
    mockup = hero_workspace_mockup()
    diagram = arch_diagram()

    cards = [
        ("discovered", "Discovered, not hand-built",
         "The model proposes the nouns and verbs of your business from your live data. "
         "You only approve or turn down. No consultants, no ontology authored by hand."),
        ("mcp", "MCP is the connector layer",
         "No proprietary connector marketplace. Any MCP-compatible client — Cursor, Claude, "
         "Hermes, your own agents — reads and writes the ontology. Quinovo also exposes itself "
         "as MCP. Bidirectional."),
        ("specialists", "Small specialists, not one giant model",
         "Filter the ontology into a dataset and train a small specialized model on just your "
         "workspace's data. Cheap, private, fast, yours."),
        ("hitl", "HITL is the only human job",
         "The loop runs itself. Below 0.8 confidence parks for your review; 0.8 and above "
         "auto-applies. Humans are approvers, not builders."),
        ("record", "The ontology is the record",
         "Dashboards are by-products of the loop, not separately built. Actions write out; "
         "they don't undo what you approved. The kernel stays the system of record."),
        ("security", "Security is a primitive",
         "Data, Logic, Action, Security. Security is first-class in the kernel, not a "
         "bolt-on added after the fact."),
    ]
    cards_html = "\n".join(
        f"""      <article class="why-card why-{key}">
        <div class="why-graphic">{why_graphic(key)}</div>
        <div class="why-copy">
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
      </article>"""
        for key, title, body in cards
    )

    primitives = [
        ("Data", "Things and how they connect. The nouns of your business, modeled as objects and links."),
        ("Logic", "Rules and inference. The verbs — what follows from what, learned and approved."),
        ("Action", "Write-backs to real systems. Named, typed, audited actions that change the world."),
        ("Security", "First-class in the kernel. Who can read, write, approve — modeled, not bolted on."),
    ]
    primitives_html = "\n".join(
        f"""      <div class="prim">
        {primitive_graphic(name)}
        <span class="prim-name">{name}</span>
        <p>{desc}</p>
      </div>"""
        for name, desc in primitives
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Quinovo — the nouns and verbs of your business, learned from your data</title>
  <meta name="description" content="Quinovo is an open-source operational ontology kernel. It learns the nouns and verbs of your business from your live data and only asks you to approve what it's not sure about. Apache-2.0."/>
  <meta name="theme-color" content="#f9f7f4"/>
  <meta property="og:title" content="Quinovo — nouns and verbs, learned from your data"/>
  <meta property="og:description" content="An open-source operational ontology kernel. The loop runs itself. You only approve. Apache-2.0."/>
  <meta property="og:type" content="website"/>
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
        <a href="#why">Why</a>
        <a href="#how">How it works</a>
        <a href="#actions">Actions</a>
        <a href="#connect">Connect</a>
        <a href="/twin">Workspace</a>
        <a href="{GITHUB_URL}" rel="noopener">GitHub</a>
      </nav>
      <a class="site-cta" href="{nav_cta_href}">{nav_cta_label}</a>
      <details class="nav-more">
        <summary>Menu</summary>
        <div class="nav-more-panel">
          <a href="#why">Why</a>
          <a href="#how">How it works</a>
          <a href="#actions">Actions</a>
          <a href="#faq">Questions</a>
          <a href="#connect">Connect</a>
          <a href="/twin">Workspace</a>
          <a href="{GITHUB_URL}" rel="noopener">Star on GitHub</a>
        </div>
      </details>
    </div>
  </header>

  <main id="main">
    <section class="hero">
      <div class="hero-split">
        <div class="hero-copy">
          <p class="kicker">Open-source operational ontology kernel</p>
          <h1>The nouns and verbs of your business, learned from your data.</h1>
          <p class="lede">
            Quinovo reads your live data, proposes the types, rules, and actions that describe
            your business, and only asks you to approve what it's not sure about. Connect any
            MCP-compatible agent to read and write it. Apache-2.0.
          </p>
          <div class="hero-cta">
            <a class="btn btn-primary" href="{hero_primary_href}">{hero_primary_label}</a>
            <a class="btn btn-ghost" href="{hero_secondary_href}">{hero_secondary_label}</a>
          </div>
          <ul class="proof">
            <li>Runs on your machine</li>
            <li>You only approve</li>
            <li>Apache-2.0</li>
          </ul>
          <div class="hero-run">
            <span class="run-label">Run locally:</span>
            <code class="run-code">uv run quinovo serve</code>
          </div>
        </div>
{mockup}
      </div>
    </section>

    <section id="why" class="why">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">Why Quinovo</p>
          <h2>A different bet than the closed, consultant-driven approach.</h2>
          <p class="section-sub">
            No rented frontier model. No ontology authored by hand. No proprietary connector
            marketplace. The kernel discovers the world from your data; you approve it.
          </p>
        </header>
        <div class="why-grid">
{cards_html}
        </div>
      </div>
    </section>

    <section id="how" class="how">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">How it works</p>
          <h2>The loop runs itself. You only approve what it is not sure about.</h2>
          <p class="section-sub">Four primitives. One kernel. Humans are approvers, not builders.</p>
        </header>
        <div class="how-tabs" role="tablist" aria-label="Kernel stages">
          <button type="button" class="how-tab on" role="tab" aria-selected="true" data-stage="data">Data</button>
          <button type="button" class="how-tab" role="tab" aria-selected="false" data-stage="logic">Logic</button>
          <button type="button" class="how-tab" role="tab" aria-selected="false" data-stage="approve">Approve</button>
          <button type="button" class="how-tab" role="tab" aria-selected="false" data-stage="action">Action</button>
        </div>
{diagram}
        <div class="primitives">
{primitives_html}
        </div>
      </div>
    </section>

{action_section_html()}

    <section id="connect" class="connect">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">Connect your agent</p>
          <h2>Quinovo speaks MCP. Point any client at it.</h2>
          <p class="section-sub">
            Quinovo exposes itself as an MCP server over stdio. Pick your agent
            below, copy the launch command, and paste it where your client asks
            for an MCP server. The button above the cards signs you in first and
            fills the real paths in for you.
          </p>
        </header>

        <div class="connect-button-row">
          <a class="btn btn-primary btn-connect" href="{connect_href}">{connect_label}</a>
          <p class="connect-button-sub">{connect_sub}</p>
        </div>

        <div class="agent-cards" id="agent-cards">
{agent_cards}
        </div>

        <div class="connect-cta">
          <p>Then open your agent and ask it to read the ontology, propose types, or run an action.</p>
          <div class="hero-cta">
            <a class="btn btn-primary" href="{connect_href}">{connect_label}</a>
            <a class="btn btn-ghost" href="/twin">Open the workspace</a>
          </div>
        </div>
      </div>
    </section>

    <section id="faq" class="faq">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">Questions</p>
          <h2>Straight answers before you connect.</h2>
        </header>
        <div class="faq-list">
          <details class="faq-item" open>
            <summary>Do I need a consultant to model the business?</summary>
            <p>No. Quinovo proposes the nouns and verbs from your live data. You approve or turn down. That is the whole human job.</p>
          </details>
          <details class="faq-item">
            <summary>Where does my data live?</summary>
            <p>On this machine. Quinovo is a local, single-user tool. The pack and the database are paths you choose. Nothing is rented as a closed platform.</p>
          </details>
          <details class="faq-item">
            <summary>What happens when Quinovo is not sure?</summary>
            <p>Below 0.8 confidence waits for you on Inference. 0.8 and above applies on its own. You are an approver, not a builder.</p>
          </details>
          <details class="faq-item">
            <summary>Which agents can connect?</summary>
            <p>Any MCP-compatible client. Cursor, Claude Desktop, Hermes, or your own agent. Quinovo also exposes itself as MCP.</p>
          </details>
          <details class="faq-item">
            <summary>Is this a closed platform?</summary>
            <p>No. Apache-2.0. Read it, run it, fork it, ship it. There is no proprietary connector marketplace.</p>
          </details>
          <details class="faq-item">
            <summary>How do small specialists work?</summary>
            <p>On Train, filter the live workspace into a set. Quinovo writes a training file for a small model on just that data. Cheap, private, yours.</p>
          </details>
        </div>
      </div>
    </section>
  </main>

  <footer class="site-foot">
    <div class="foot-inner">
      <div class="foot-brand">
        <a class="brand" href="/">{BRICKS_ON_DARK}<span class="brand-name">quinovo</span></a>
        <p class="foot-tag">Operational ontology kernel. Apache-2.0.</p>
      </div>
      <nav class="foot-nav">
        <a href="{GITHUB_URL}" rel="noopener">GitHub</a>
        <a href="/twin">Workspace</a>
        <a href="/settings">Settings</a>
        <a href="/train">Train</a>
      </nav>
      <p class="foot-credit">built by <a href="{GITHUB_URL}" rel="noopener">cfollette18</a></p>
    </div>
  </footer>
  <script>
  (function () {{
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
        if (input) copyText(input.value, btn);
      }});
    }});
    document.querySelectorAll("[data-motion-pause]").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        var on = document.documentElement.classList.toggle("motion-paused");
        document.querySelectorAll("[data-motion-pause]").forEach(function (b) {{
          b.textContent = on ? "Play motion" : "Pause motion";
          b.setAttribute("aria-pressed", on ? "true" : "false");
        }});
      }});
    }});
    var how = document.getElementById("how");
    var tabs = document.querySelectorAll(".how-tab");
    tabs.forEach(function (tab) {{
      tab.addEventListener("click", function () {{
        tabs.forEach(function (t) {{
          t.classList.toggle("on", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        }});
        if (how) how.setAttribute("data-stage", tab.getAttribute("data-stage") || "data");
      }});
    }});
    if (how) how.setAttribute("data-stage", "data");
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {{
      var io = new IntersectionObserver(function (entries) {{
        entries.forEach(function (e) {{
          if (e.isIntersecting) {{
            e.target.classList.add("in");
            io.unobserve(e.target);
          }}
        }});
      }}, {{ threshold: 0.12 }});
      document.querySelectorAll(".why, .how, .actions, .connect, .faq").forEach(function (el) {{
        el.classList.add("reveal");
        io.observe(el);
      }});
    }}
  }})();
  </script>
</body>
</html>"""
