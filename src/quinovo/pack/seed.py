"""Seed YAML schema: the objects and links a pack loads on first boot.

Seed objects are keyed by object type; each row is a property mapping that
must include the type's primary key. Seed links are keyed by link type and
name their endpoints with from_id/to_id — the endpoint types come from the
link type definition, so they are never repeated here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from quinovo.language.models import QuinovoModel


class SeedLink(QuinovoModel):
    """One seeded link: two object ids, typed by the link type definition."""

    from_id: str
    to_id: str


class SeedDoc(QuinovoModel):
    objects: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    links: dict[str, list[SeedLink]] = Field(default_factory=dict)


def load_seed_doc(path: str | Path) -> SeedDoc:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: seed file must be a mapping")
    return SeedDoc.model_validate(data)
