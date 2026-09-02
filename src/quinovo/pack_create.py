"""quinovo.pack_create — scaffold a new pack from a spec dict or YAML.

This is the only sanctioned way to author a pack from code. The spec is
validated through the same loaders the kernel uses (load_ontology,
load_ruleset) — a bad spec fails immediately, no half-written pack left
on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quinovo.inference.load import load_ruleset
from quinovo.language.load import load_ontology


class PackCreateError(ValueError):
    """Pack spec rejected before files are written."""


def create_pack(dest: Path, spec: dict[str, Any]) -> Path:
    """Write ontology.yaml, optional inference.yaml, optional seed.yaml
    into `dest`. Validate by loading through the real loaders.

    Raises PackCreateError for caller-fixable problems (missing ontology,
    non-empty dest). Raises whatever the loaders raise for spec-fixable
    problems — those bubble up unchanged so the caller sees the exact
    Pydantic message.
    """
    if not isinstance(spec, dict):
        raise PackCreateError("spec must be a mapping")
    if "ontology" not in spec:
        raise PackCreateError("spec missing 'ontology'")
    if not isinstance(spec["ontology"], dict):
        raise PackCreateError("spec.ontology must be a mapping")

    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise PackCreateError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)

    # spec["ontology"] is the full ontology document shape that load_ontology
    # expects: top-level keys are `ontology` (meta) plus `object_types`,
    # `link_types`, `action_types`, etc. If a caller passes only the inner
    # OntologyMeta (`api_name`, `display_name`, ...), wrap it.
    ontology_doc = dict(spec["ontology"])
    if "ontology" not in ontology_doc:
        ontology_doc = {"ontology": ontology_doc}
    (dest / "ontology.yaml").write_text(
        yaml.safe_dump(ontology_doc, sort_keys=False), encoding="utf-8"
    )
    if "inference" in spec:
        (dest / "inference.yaml").write_text(
            yaml.safe_dump(spec["inference"], sort_keys=False), encoding="utf-8"
        )
    if "seed" in spec:
        (dest / "seed.yaml").write_text(
            yaml.safe_dump(spec["seed"], sort_keys=False), encoding="utf-8"
        )

    # Validate through the real loaders. If the spec is malformed, this
    # raises — and the half-written pack stays on disk for inspection.
    # That's intentional: an empty pack is harder to debug than a pack
    # that failed validation.
    load_ontology(dest / "ontology.yaml")
    if "inference" in spec:
        load_ruleset(dest / "inference.yaml")
    return dest


def create_pack_from_yaml(dest: Path, spec_path: Path) -> Path:
    """Convenience wrapper: read spec from a YAML file, then create_pack."""
    raw = spec_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise PackCreateError(f"{spec_path}: spec must be a YAML mapping at top level")
    return create_pack(dest, data)
