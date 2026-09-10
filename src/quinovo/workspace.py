"""Empty local workspace. No teaching nouns. Types arrive as proposals.

Also owns project-root discovery and the default pack/db paths.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def discover_root() -> Path:
    """Find the Quinovo project root by looking for a packs/ directory.

    Any pack directory with an ontology.yaml counts as proof we're in a
    Quinovo checkout. We do not hardcode a pack name; the world is what
    the user has loaded, not a fixed example.
    """
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        packs = candidate / "packs"
        if packs.is_dir() and any(packs.glob("*/ontology.yaml")):
            return candidate
    raise FileNotFoundError(
        "could not find a Quinovo checkout: no packs/*/ontology.yaml"
    )


def _first_pack() -> Path:
    """Return the first pack that ships an ontology.yaml. Used as a
    fallback default for commands that take --pack but the user did not
    pass one. Order is alphabetical so behavior is deterministic."""
    packs = ROOT / "packs"
    candidates = sorted(packs.glob("*/ontology.yaml"))
    if not candidates:
        raise FileNotFoundError(f"no packs found under {packs}")
    return candidates[0].parent


ROOT = discover_root()
DEFAULT_PACK = _first_pack()
WORLD_PACK = ROOT / "packs" / "world"
EXAMPLE_PACK = WORLD_PACK
DEFAULT_DB = ROOT / ".data" / "quinovo.sqlite"

WORKSPACE_ROOT = ROOT / ".data" / "workspace"
WORKSPACE_PACK = WORKSPACE_ROOT / "pack"
WORKSPACE_DB = WORKSPACE_ROOT / "quinovo.sqlite"

BLANK_ONTOLOGY = {
    "ontology": {
        "api_name": "workspace",
        "display_name": "Workspace",
        "description": (
            "Empty operational ontology. Object types, links, actions, and rules "
            "arrive as proposals. You only approve or reject."
        ),
        "auto_apply_min_confidence": 0.8,
    },
    "object_types": [],
    "link_types": [],
    "action_types": [],
}


def ensure_workspace(*, reset: bool = False) -> tuple[Path, Path]:
    if reset and WORKSPACE_ROOT.exists():
        import shutil

        shutil.rmtree(WORKSPACE_ROOT)
    WORKSPACE_PACK.mkdir(parents=True, exist_ok=True)
    ont = WORKSPACE_PACK / "ontology.yaml"
    if not ont.exists():
        ont.write_text(yaml.safe_dump(BLANK_ONTOLOGY, sort_keys=False), encoding="utf-8")
    WORKSPACE_DB.parent.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_PACK, WORKSPACE_DB


def resolve_serve_paths(
    pack: Path | None = None,
    db: Path | None = None,
) -> tuple[Path, Path]:
    """quinovo serve uses the empty workspace unless a pack is passed."""
    if pack is None:
        ws_pack, ws_db = ensure_workspace()
        return ws_pack, db or ws_db
    return pack, db or DEFAULT_DB
