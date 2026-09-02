from __future__ import annotations

from pathlib import Path

import yaml

from quinovo.inference.rules import InferenceRuleset


def load_ruleset(path: str | Path) -> InferenceRuleset:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: inference file must be a mapping")
    return InferenceRuleset.model_validate(data)
