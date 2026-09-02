from __future__ import annotations

from pathlib import Path


def discover_root() -> Path:
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        if (candidate / "packs" / "example" / "ontology.yaml").exists():
            return candidate
    raise FileNotFoundError("could not find packs/example/ontology.yaml")


ROOT = discover_root()
EXAMPLE_PACK = ROOT / "packs" / "example"
CLINIC_PACK = ROOT / "packs" / "clinic"
DEFAULT_DB = ROOT / ".data" / "quinovo.sqlite"
