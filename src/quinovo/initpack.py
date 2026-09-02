"""Copy a starter pack. Strangers get example, not homelab."""

from __future__ import annotations

import shutil
from pathlib import Path

from quinovo.paths import EXAMPLE_PACK, ROOT

STARTERS = {"example": EXAMPLE_PACK, "clinic": ROOT / "packs" / "clinic"}


def init_pack(dest: Path, starter: str = "example") -> Path:
    source = STARTERS.get(starter)
    if source is None or not source.exists():
        raise FileNotFoundError(
            f"unknown starter {starter!r}. Use example (or clinic). Homelab is dogfood, not a template."
        )
    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    return dest
