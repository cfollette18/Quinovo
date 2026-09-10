"""Agent connection cards: logos, blurbs, and plain-language connect steps.

The Quinovo frontend never shows raw JSON to users. This module is the single
source of truth for the MCP-compatible agents a user can connect to. Each
agent is rendered as a logo card; the connection steps are plain language and
the launch command is a single line in a styled input box. The full config a
power user needs is fetched from the API on copy, never rendered as a JSON
block on the page.

Used by the public landing page (placeholder paths) and the signed-in guided
connect flow (real paths filled in).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AGENTS", "AGENT_IDS", "agent_by_id", "launch_command", "logo_svg"]


# Local marks under /assets/agents/. Cursor, Claude, and MCP are Simple Icons
# SVGs (still in the current collection). Hermes has no public trademark SVG
# we can ship — the caduceus is a distinctive Hermes Agent mark.
_LOGO_FILES: dict[str, str] = {
    "cursor": "cursor.svg",
    "claude": "claude.svg",
    "hermes": "hermes.svg",
    "other": "mcp.svg",
}


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    blurb: str
    where: str
    steps: str  # plain-language, HTML-safe (already escaped where needed)


AGENTS: list[Agent] = [
    Agent(
        id="cursor",
        name="Cursor",
        blurb="The AI code editor. Add Quinovo as an MCP server and your agent reads and writes the ontology.",
        where=".cursor/mcp.json (this project) or ~/.cursor/mcp.json (user-wide)",
        steps=(
            "Open the project in Cursor. Create or edit "
            "<code>.cursor/mcp.json</code> at the project root (or "
            "<code>~/.cursor/mcp.json</code> to add it everywhere). Paste the "
            "config the copy button gives you. Restart Cursor, then open the "
            "agent panel — Quinovo will appear as an MCP server it can call."
        ),
    ),
    Agent(
        id="claude",
        name="Claude Desktop",
        blurb="Anthropic’s desktop app. Quinovo shows up under Developer tools.",
        where="claude_desktop_config.json",
        steps=(
            "Quit Claude Desktop. Open (or create) the config file at the path "
            "shown. Paste the config the copy button gives you. Save, then "
            "relaunch Claude Desktop. Quinovo shows up under "
            "<em>Developer</em> tools."
        ),
    ),
    Agent(
        id="hermes",
        name="Hermes",
        blurb="A multi-model agent runtime. Reads MCP servers from a YAML config.",
        where="~/.hermes/config.yaml (under mcp_servers:)",
        steps=(
            "Hermes reads MCP servers from <code>~/.hermes/config.yaml</code> "
            "under <code>mcp_servers:</code>. Easiest is "
            "<code>hermes mcp add quinovo --command uv --args run --args quinovo "
            "--args mcp --args --pack --args &lt;pack&gt; --args --db --args "
            "&lt;db&gt;</code>. Or paste the YAML the copy button gives you into "
            "that file. From an open session, <code>/reload-mcp</code> picks it "
            "up without losing your prompt cache."
        ),
    ),
    Agent(
        id="other",
        name="Other (any MCP client)",
        blurb="Anything that speaks MCP over stdio — VS Code, Zed, Windsurf, your own agent.",
        where="Your client's MCP config",
        steps=(
            "Any client that speaks MCP over stdio can connect. Run the command "
            "shown as the MCP server process; pass its stdio to your client the "
            "way its docs describe. The <code>--pack</code> path is the world "
            "Quinovo models; the <code>--db</code> path is where it stores facts."
        ),
    ),
]

AGENT_IDS = [a.id for a in AGENTS]


def agent_by_id(agent_id: str) -> Agent | None:
    for a in AGENTS:
        if a.id == agent_id:
            return a
    return None


def logo_svg(agent_id: str) -> str:
    """Return an <img> pointing at the local agent mark. Never inline JSON."""
    name = _LOGO_FILES.get(agent_id, _LOGO_FILES["other"])
    return (
        f'<img src="/assets/agents/{name}" alt="" width="28" height="28" '
        f'decoding="async"/>'
    )


def launch_command(pack: str, db: str) -> str:
    """Single-line launch command shown in the styled input box."""
    return f'uv run quinovo mcp --pack "{pack}" --db "{db}"'
