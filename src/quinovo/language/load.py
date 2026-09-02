from __future__ import annotations

from pathlib import Path

import yaml

from quinovo.language.models import Ontology


def load_ontology(path: str | Path) -> Ontology:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: ontology file must be a mapping")
    return Ontology.model_validate(data)
