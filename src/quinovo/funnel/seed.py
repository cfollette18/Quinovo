"""Load a pack's seed.yaml into the store. Not a live connector."""

from __future__ import annotations

from pathlib import Path

from quinovo.engine.store import ObjectStore
from quinovo.pack.seed import load_seed_doc


def load_seed(store: ObjectStore, path: str | Path) -> None:
    """Upsert seed objects, then link them. Idempotent on reload."""
    seed = load_seed_doc(path)
    for object_type, rows in seed.objects.items():
        for row in rows:
            store.upsert_object(object_type, row)
    for link_type, rows in seed.links.items():
        spec = store.ontology.link_type(link_type)
        for row in rows:
            store.add_link(
                link_type,
                spec.from_type,
                row.from_id,
                spec.to_type,
                row.to_id,
            )
