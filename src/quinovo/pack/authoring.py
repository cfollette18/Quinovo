"""Pack YAML read/write. Validated through the same loaders the kernel uses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quinovo.engine.store import ObjectStore, StoredObject
from quinovo.inference.rules import InferenceRule
from quinovo.language.models import (
    PROPOSAL_KINDS,
    ActionTypeDef,
    LinkTypeDef,
    ObjectTypeDef,
)
from quinovo.pack.create import PackCreateError, create_pack
from quinovo.pack.validate import validate_pack

PACK_FILES = (
    "ontology.yaml",
    "inference.yaml",
    "security.yaml",
    "seed.yaml",
    "functions.yaml",
)


def read_pack(pack_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name in PACK_FILES:
        path = pack_dir / name
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        files[name] = data
    return {"path": str(pack_dir.resolve()), "files": files}


def write_pack_document(pack_dir: Path, filename: str, document: dict[str, Any]) -> Path:
    if filename not in PACK_FILES:
        raise PackCreateError(f"unknown pack file {filename!r}")
    if not isinstance(document, dict):
        raise PackCreateError(f"{filename} must be a mapping")
    pack_dir = pack_dir.resolve()
    pack_dir.mkdir(parents=True, exist_ok=True)
    target = pack_dir / filename
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    try:
        _validate(pack_dir, filename)
    except Exception:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(previous, encoding="utf-8")
        raise
    return target


def _validate(pack_dir: Path, filename: str) -> None:
    match filename:
        case "ontology.yaml" | "inference.yaml" | "security.yaml" | "seed.yaml":
            validate_pack(pack_dir)
        case "functions.yaml":
            # Lazy: logic.functions → engine.payloads → ai.runtime → pack.authoring
            # is still an import cycle, so this cannot be a top-level import yet.
            from quinovo.logic.functions import load_functions

            load_functions(pack_dir / filename)
        case _ as unreachable:
            raise AssertionError(f"unhandled pack file {unreachable}")


def merge_ontology_entry(pack_dir: Path, section: str, entry: dict[str, Any]) -> Path:
    """Replace or append one object/link/action type in ontology.yaml by api_name."""
    match section:
        case "object_types" | "link_types" | "action_types":
            pass
        case _ as unreachable:
            raise PackCreateError(f"cannot merge into {unreachable!r}")
    path = pack_dir / "ontology.yaml"
    if not path.exists():
        raise PackCreateError("pack has no ontology.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PackCreateError("ontology.yaml must be a mapping")
    api_name = entry.get("api_name")
    if not isinstance(api_name, str) or not api_name:
        raise PackCreateError("entry needs api_name")
    items = list(data.get(section) or [])
    merged: list[Any] = []
    replaced = False
    for item in items:
        if isinstance(item, dict) and item.get("api_name") == api_name:
            merged.append(entry)
            replaced = True
        else:
            merged.append(item)
    if not replaced:
        merged.append(entry)
    data[section] = merged
    return write_pack_document(pack_dir, "ontology.yaml", data)


def merge_inference_rule(pack_dir: Path, rule: dict[str, Any]) -> Path:
    """Replace or append one rule in inference.yaml by api_name."""
    api_name = rule.get("api_name")
    if not isinstance(api_name, str) or not api_name:
        raise PackCreateError("rule needs api_name")
    path = pack_dir / "inference.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise PackCreateError("inference.yaml must be a mapping")
    else:
        data = {}
    rules = list(data.get("rules") or [])
    merged: list[Any] = []
    replaced = False
    for item in rules:
        if isinstance(item, dict) and item.get("api_name") == api_name:
            merged.append(rule)
            replaced = True
        else:
            merged.append(item)
    if not replaced:
        merged.append(rule)
    data["rules"] = merged
    return write_pack_document(pack_dir, "inference.yaml", data)


def apply_kind(
    pack_dir: Path,
    store: ObjectStore,
    kind: str,
    payload: dict[str, Any],
) -> tuple[list[StoredObject], bool]:
    """Apply an approved or auto-applied proposal. True means the kernel must reload."""
    payload = dict(payload)
    payload.pop("reason", None)
    match kind:
        case "type_definition":
            type_def = ObjectTypeDef.model_validate(payload)
            merge_ontology_entry(pack_dir, "object_types", type_def.model_dump())
            return [], True
        case "classification":
            object_type = payload.get("object_type")
            properties = payload.get("properties")
            if not isinstance(object_type, str) or not isinstance(properties, dict):
                raise PackCreateError("classification payload needs object_type and properties")
            return [store.upsert_object(object_type, properties)], False
        case "inference_rule":
            rule = InferenceRule.model_validate(payload)
            merge_inference_rule(pack_dir, rule.model_dump(exclude_none=True))
            return [], True
        case "link_type":
            link = LinkTypeDef.model_validate(payload)
            merge_ontology_entry(pack_dir, "link_types", link.model_dump())
            return [], True
        case "action_type":
            action = ActionTypeDef.model_validate(payload)
            merge_ontology_entry(pack_dir, "action_types", action.model_dump())
            return [], True
        case "action_application":
            raise PackCreateError(
                "action_application is applied by the kernel (apply_action), not by apply_kind"
            )
        case "pack":
            dest = payload.get("dest")
            spec = payload.get("spec")
            if not isinstance(dest, str) or not dest:
                raise PackCreateError("pack payload needs dest")
            if not isinstance(spec, dict):
                raise PackCreateError("pack payload needs spec mapping")
            create_pack(Path(dest), spec)
            return [], False
        case _ as unreachable:
            raise PackCreateError(
                f"unknown proposal kind {unreachable!r}; known kinds: {sorted(PROPOSAL_KINDS)}"
            )


__all__ = [
    "PACK_FILES",
    "PackCreateError",
    "apply_kind",
    "create_pack",
    "merge_inference_rule",
    "merge_ontology_entry",
    "read_pack",
    "write_pack_document",
]
