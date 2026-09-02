"""Sandboxed pack functions. No disk, no SQL, no imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from quinovo.engine.store import ObjectStore


class FunctionError(Exception):
    pass


class FunctionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_name: str
    source: str
    description: str = ""


class FunctionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    functions: list[FunctionDef] = Field(default_factory=list)


def load_functions(path: str | Path) -> FunctionManifest:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    return FunctionManifest.model_validate(data)


def run_function(
    store: ObjectStore,
    pack_dir: Path,
    spec: FunctionDef,
    args: dict[str, Any],
) -> Any:
    path = pack_dir / spec.source
    source = path.read_text(encoding="utf-8")
    if "import " in source or "__" in source or "open(" in source:
        raise FunctionError(f"{spec.api_name}: disallowed token in function source")

    def get_object(object_type: str, pk: str) -> dict[str, Any] | None:
        obj = store.get_object(object_type, pk)
        if obj is None:
            return None
        return {"type": obj.object_type, "id": obj.primary_key, "properties": obj.properties}

    def search_around(object_type: str, pk: str, side: str) -> list[dict[str, Any]]:
        return [
            {"type": item.object_type, "id": item.primary_key, "properties": item.properties}
            for item in store.search_around(object_type, pk, side)
        ]

    def list_objects(object_type: str) -> list[dict[str, Any]]:
        return [
            {"type": item.object_type, "id": item.primary_key, "properties": item.properties}
            for item in store.list_objects(object_type)
        ]

    ns: dict[str, Any] = {
        "__builtins__": {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "list": list,
            "dict": dict,
            "True": True,
            "False": False,
            "None": None,
            "range": range,
            "enumerate": enumerate,
            "min": min,
            "max": max,
        },
        "args": args,
        "get_object": get_object,
        "search_around": search_around,
        "list_objects": list_objects,
        "result": None,
    }
    exec(compile(source, str(path), "exec"), ns, ns)  # noqa: S102
    return ns.get("result")
