"""Propose object types from messy files. Suggestions only — HITL below 80%."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from quinovo.ai.runtime import submit_proposal
from quinovo.engine.store import ObjectStore


HEADING = re.compile(r"^#+\s+([A-Z][A-Za-z0-9]+)\s*$", re.MULTILINE)
FIELD = re.compile(r"^[-*]\s+`?([a-z][a-z0-9_]+)`?", re.MULTILINE)


def extract_types(root: Path) -> list[dict[str, Any]]:
    proposed: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for heading in HEADING.findall(text):
            fields = FIELD.findall(text)
            props = [{"api_name": "id", "type": "string"}]
            for name in fields[:8]:
                if name == "id":
                    continue
                props.append({"api_name": name, "type": "string", "required": False})
            proposed.append(
                {
                    "api_name": heading,
                    "primary_key": "id",
                    "title_property": "id",
                    "description": f"Proposed from {path.name}",
                    "properties": props,
                }
            )
    return proposed


def propose_from_files(
    store: ObjectStore,
    root: Path,
    confidence: float,
    actor: str = "quinovo-proposer",
) -> list[Any]:
    out = []
    for type_def in extract_types(root):
        proposal, _edited = submit_proposal(store, "type_definition", type_def, confidence, actor)
        out.append(proposal)
    return out
