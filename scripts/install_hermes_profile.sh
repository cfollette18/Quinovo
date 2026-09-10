#!/usr/bin/env bash
# install_hermes_profile.sh — install the `quinovo` Hermes profile.
#
# Copies integrations/hermes-profile/ into ~/.hermes/:
#   profile files  -> ~/.hermes/profiles/quinovo/
#   skill          -> ~/.hermes/skills/mcp/using-quinovo/
#   rule           -> ~/.hermes/rules/01-quinovo-is-the-world.mdc
#
# Verifies the MCP server config exists at ~/.hermes/mcp/servers/quinovo.md
# (warns, never overwrites). Idempotent: re-running updates the copies.
#
# Usage:
#   scripts/install_hermes_profile.sh              install / update
#   scripts/install_hermes_profile.sh --uninstall  remove installed copies
#
# Profile runtime state (sessions/, state.db, ...) under
# ~/.hermes/profiles/quinovo/ is never touched.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/integrations/hermes-profile"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

PROFILE_DIR="$HERMES_HOME/profiles/quinovo"
SKILL_DIR="$HERMES_HOME/skills/mcp/using-quinovo"
RULES_DIR="$HERMES_HOME/rules"
MCP_SERVER_MD="$HERMES_HOME/mcp/servers/quinovo.md"

PROFILE_FILES=(profile.yaml SOUL.md AGENTS.md config.yaml distribution.yaml skills.lock)

info() { printf 'install: %s\n' "$*"; }
warn() { printf 'install: WARNING: %s\n' "$*" >&2; }

uninstall() {
  local f
  for f in "${PROFILE_FILES[@]}"; do
    if [[ -f "$PROFILE_DIR/$f" ]]; then
      rm "$PROFILE_DIR/$f"
      info "removed $PROFILE_DIR/$f"
    fi
  done
  if [[ -d "$PROFILE_DIR/skills" ]]; then
    rm -rf "$PROFILE_DIR/skills"
    info "removed $PROFILE_DIR/skills"
  fi
  if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
    rm "$SKILL_DIR/SKILL.md"
    info "removed $SKILL_DIR/SKILL.md"
  fi
  if [[ -f "$RULES_DIR/01-quinovo-is-the-world.mdc" ]]; then
    rm "$RULES_DIR/01-quinovo-is-the-world.mdc"
    info "removed $RULES_DIR/01-quinovo-is-the-world.mdc"
  fi
  if [[ -d "$PROFILE_DIR" ]]; then
    warn "left $PROFILE_DIR in place (runtime state: sessions, state.db). Remove it by hand if unwanted."
  fi
  info "uninstall complete"
}

install() {
  [[ -d "$SRC" ]] || { warn "source tree not found: $SRC"; exit 1; }

  mkdir -p "$PROFILE_DIR/skills" "$SKILL_DIR" "$RULES_DIR"

  local f
  for f in "${PROFILE_FILES[@]}"; do
    cp "$SRC/$f" "$PROFILE_DIR/$f"
    info "installed $PROFILE_DIR/$f"
  done
  cp -R "$SRC/skills/." "$PROFILE_DIR/skills/"
  info "installed $PROFILE_DIR/skills/"

  cp "$SRC/skills/using-quinovo/SKILL.md" "$SKILL_DIR/SKILL.md"
  info "installed $SKILL_DIR/SKILL.md"

  cp "$SRC/rules/01-quinovo-is-the-world.mdc" "$RULES_DIR/01-quinovo-is-the-world.mdc"
  info "installed $RULES_DIR/01-quinovo-is-the-world.mdc"

  if [[ -f "$MCP_SERVER_MD" ]]; then
    info "MCP server config found: $MCP_SERVER_MD (left as-is)"
  else
    warn "MCP server config not found: $MCP_SERVER_MD"
    warn "register the quinovo server before starting the profile, e.g.:"
    warn "  hermes mcp add quinovo --command $REPO_ROOT/.venv/bin/quinovo -- mcp --pack $REPO_ROOT/packs/world --db $REPO_ROOT/.data/world.sqlite"
  fi

  cat <<'EOF'

Next steps:
  1. Restart Hermes or run `/reload-mcp` so the quinovo server connects.
  2. Start the profile: hermes --profile quinovo
  3. Ask about the world — the agent answers from the twin and acts only
     through apply_action. Pending items stay in the review queue for a human.
  4. Wake-on-event wiring (Quinovo outbound hook -> Hermes) is documented in
     integrations/hermes-profile/README.md.
EOF
}

case "${1:-}" in
  --uninstall) uninstall ;;
  "") install ;;
  *) warn "unknown flag: $1 (expected --uninstall)"; exit 2 ;;
esac
