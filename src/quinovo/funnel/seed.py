from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quinovo.engine.store import ObjectStore


def load_seed(store: ObjectStore, path: str | Path) -> None:
    """v0.1 Funnel: JSON/YAML objects+links into the index. Not a live connector."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: seed must be a mapping")
    objects = data.get("objects") or {}
    if not isinstance(objects, dict):
        raise ValueError("seed.objects must be a mapping of type -> list")
    for object_type, rows in objects.items():
        if not isinstance(rows, list):
            raise ValueError(f"seed.objects.{object_type} must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"seed.objects.{object_type} entries must be mappings")
            store.upsert_object(str(object_type), row)

    links = data.get("links") or {}
    if not isinstance(links, dict):
        raise ValueError("seed.links must be a mapping of link type -> list")
    for link_type, rows in links.items():
        if not isinstance(rows, list):
            raise ValueError(f"seed.links.{link_type} must be a list")
        spec = store.ontology.link_type(str(link_type))
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"seed.links.{link_type} entries must be mappings")
            from_ref = _ref(row.get("from"), spec.from_type)
            to_ref = _ref(row.get("to"), spec.to_type)
            store.add_link(
                str(link_type),
                from_ref["type"],
                from_ref["id"],
                to_ref["type"],
                to_ref["id"],
            )


def _ref(value: Any, default_type: str) -> dict[str, str]:
    if isinstance(value, str):
        return {"type": default_type, "id": value}
    if isinstance(value, dict) and "id" in value:
        return {
            "type": str(value.get("type", default_type)),
            "id": str(value["id"]),
        }
    raise ValueError(f"link endpoint must be an id string or {{type, id}}, got {value!r}")
