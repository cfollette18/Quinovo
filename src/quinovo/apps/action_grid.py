"""Landing Action-layer grid: write-back targets and universal adapters.

Tiles name the ERPs, CRMs, and project tools teams already run. Quinovo
reaches them through HTTP, webhook, SQL, Slack, email, and MCP — not a
marketplace of 300 native connectors. No raw JSON.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ACTION_SYSTEMS", "action_section_html"]


@dataclass(frozen=True)
class ActionSystem:
    id: str
    name: str
    category: str
    src: str


ACTION_SYSTEMS: tuple[ActionSystem, ...] = (
    ActionSystem("sap", "SAP", "ERP", "/assets/actions/sap.svg"),
    ActionSystem("netsuite", "NetSuite", "ERP", "/assets/actions/netsuite.svg"),
    ActionSystem("oracle", "Oracle", "ERP", "/assets/actions/oracle.svg"),
    ActionSystem("dynamics", "Dynamics", "ERP", "/assets/actions/dynamics.svg"),
    ActionSystem("odoo", "Odoo", "ERP", "/assets/actions/odoo.svg"),
    ActionSystem("salesforce", "Salesforce", "CRM", "/assets/actions/salesforce.svg"),
    ActionSystem("hubspot", "HubSpot", "CRM", "/assets/actions/hubspot.svg"),
    ActionSystem("pipedrive", "Pipedrive", "CRM", "/assets/actions/pipedrive.svg"),
    ActionSystem("zendesk", "Zendesk", "CRM", "/assets/actions/zendesk.svg"),
    ActionSystem("jira", "Jira", "PM", "/assets/actions/jira.svg"),
    ActionSystem("linear", "Linear", "PM", "/assets/actions/linear.svg"),
    ActionSystem("asana", "Asana", "PM", "/assets/actions/asana.svg"),
    ActionSystem("monday", "Monday", "PM", "/assets/actions/monday.svg"),
    ActionSystem("notion", "Notion", "PM", "/assets/actions/notion.svg"),
    ActionSystem("slack", "Slack", "Comms", "/assets/actions/slack.svg"),
    ActionSystem("email", "Email", "Comms", "/assets/actions/email.svg"),
    ActionSystem("teams", "Teams", "Comms", "/assets/actions/teams.svg"),
    ActionSystem("postgres", "Postgres", "Data", "/assets/actions/postgres.svg"),
    ActionSystem("snowflake", "Snowflake", "Data", "/assets/actions/snowflake.svg"),
    ActionSystem("webhook", "Webhook", "Data", "/assets/actions/webhook.svg"),
    ActionSystem("http", "HTTP", "Data", "/assets/actions/http.svg"),
    ActionSystem("sql", "SQL", "Data", "/assets/actions/sql.svg"),
    ActionSystem("mcp", "MCP tools", "Agents", "/assets/actions/mcp.svg"),
)

_CATEGORY_ORDER = ("ERP", "CRM", "PM", "Comms", "Data", "Agents")


def _writeback_diagram() -> str:
    """Geometric write-back: Approve → Action → adapters → systems.

    One horizontal rail, four stops, clean orthogonal connectors. The Action
    node is the Lava focal; adapters fan into three system targets.
    """
    return """
        <figure class="act-diagram" aria-hidden="true">
          <svg class="act-svg" viewBox="0 0 1040 160" xmlns="http://www.w3.org/2000/svg">
            <title>Approved actions write back through adapters</title>
            <rect class="act-node" x="36" y="52" width="120" height="56" rx="2"/>
            <text class="act-label" x="96" y="85">Approve</text>
            <path class="act-pipe flow-pipe" d="M156 80 H236"/>
            <rect class="act-node act-hot" x="236" y="52" width="120" height="56" rx="2"/>
            <text class="act-label act-label-hot" x="296" y="85">Action</text>
            <path class="act-pipe flow-pipe" d="M356 80 H436"/>
            <g class="act-adapters">
              <rect class="act-node" x="436" y="20" width="88" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="480" y="43">HTTP</text>
              <rect class="act-node" x="436" y="68" width="88" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="480" y="91">SQL</text>
              <rect class="act-node" x="436" y="116" width="88" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="480" y="139">MCP</text>
            </g>
            <path class="act-pipe flow-pipe" d="M524 38 H624 M624 38 V64"/>
            <path class="act-pipe flow-pipe" d="M524 86 H624"/>
            <path class="act-pipe flow-pipe" d="M524 134 H624 M624 134 V108"/>
            <g class="act-systems">
              <rect class="act-node" x="624" y="28" width="96" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="672" y="51">ERP</text>
              <rect class="act-node" x="624" y="68" width="96" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="672" y="91">CRM</text>
              <rect class="act-node" x="624" y="108" width="96" height="36" rx="2"/>
              <text class="act-label act-label-sm" x="672" y="131">PM</text>
            </g>
          </svg>
        </figure>"""


def _tile(system: ActionSystem) -> str:
    return (
        f'<li class="act-tile">'
        f'<span class="act-logo">'
        f'<img src="{system.src}" alt="" width="28" height="28" decoding="async"/>'
        f"</span>"
        f'<span class="act-name">{system.name}</span>'
        f'<span class="act-cat">{system.category}</span>'
        f"</li>"
    )


def _category_row(category: str, systems: list[ActionSystem]) -> str:
    tiles = "".join(_tile(s) for s in systems)
    return f"""
        <div class="act-row">
          <h3 class="act-row-title">{category}</h3>
          <ul class="act-grid" aria-label="{category} systems">
            {tiles}
          </ul>
        </div>"""


def action_section_html() -> str:
    """Full Action-layer landing section (white band after How it works)."""
    grouped: dict[str, list[ActionSystem]] = {key: [] for key in _CATEGORY_ORDER}
    for system in ACTION_SYSTEMS:
        grouped[system.category].append(system)
    rows = "".join(_category_row(key, grouped[key]) for key in _CATEGORY_ORDER)
    return f"""    <section id="actions" class="actions">
      <div class="section-inner">
        <header class="section-head">
          <p class="kicker">Action layer</p>
          <h2>Actions write back to the tools you already run.</h2>
          <p class="section-sub">
            ERP, CRM, PM — the same verbs. Quinovo connects through universal adapters
            and MCP: HTTP, webhook, SQL, Slack, email, and MCP tools. Any system that
            speaks those protocols, or ships an MCP server, can be a write-back
            target. We do not pretend to ship 300 native connectors.
          </p>
        </header>
{_writeback_diagram()}
        <div class="act-rows">
{rows}
        </div>
      </div>
    </section>"""
