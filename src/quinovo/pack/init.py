"""Copy a starter pack. Default is the world teaching pack."""

from __future__ import annotations

import shutil
from pathlib import Path

from quinovo.workspace import DEFAULT_PACK

STARTERS = {"world": DEFAULT_PACK}


def init_pack(dest: Path, starter: str = "world") -> Path:
    source = STARTERS.get(starter)
    if source is None or not source.exists():
        raise FileNotFoundError(
            f"unknown starter {starter!r}. Use world."
        )
    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    return dest
