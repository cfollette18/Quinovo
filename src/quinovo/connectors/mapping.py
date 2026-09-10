"""Shared row mapping for every data source kind.

A source maps external rows onto one object type. The mapping is always
the same shape: optional dotted path to a list, optional field rename,
optional id field. Connectors fetch; this module turns rows into objects.
"""

from __future__ import annotations

from typing import Any

import httpx

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.engine.store import ObjectStore


def parse_property_map(text: str) -> dict[str, str]:
    """Parse a human field map: one ``from → to`` (or ``->`` / ``=``) per line."""
    mapping: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        separator = next((item for item in ("→", "->", "=") if item in line), "")
        if not separator:
            mapping[line] = line
            continue
        left, right = line.split(separator, 1)
        source = left.strip()
        target = right.strip()
        if source and target:
            mapping[source] = target
    return mapping


def extract_rows(payload: Any, rows_path: str | None = None, *, singleton: bool = False) -> list[Any]:
    """Pull a list of row dicts out of a JSON payload."""
    if rows_path:
        cursor: Any = payload
        for part in str(rows_path).split("."):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                return []
        if isinstance(cursor, list):
            return cursor
        return [cursor] if singleton and isinstance(cursor, dict) else []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "results", "objects"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if singleton:
            return [payload]
    return []


def mapped_properties(
    row: dict[str, Any],
    record: SourceRecord,
    primary_key: str,
) -> dict[str, Any]:
    """Rename fields and copy ``id_field`` onto the object primary key."""
    prop_map = record.config.get("property_map") or {}
    if not isinstance(prop_map, dict):
        raise ConnectorError("property_map must be a mapping")
    props: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        name = str(key)
        props[str(prop_map.get(name, name))] = value
    id_field = record.config.get("id_field")
    if isinstance(id_field, str) and id_field:
        raw = row.get(id_field)
        if raw is not None and primary_key not in props:
            props[primary_key] = raw
        if id_field != primary_key and id_field not in prop_map and id_field in props:
            del props[id_field]
    return props


def upsert_rows(
    store: ObjectStore,
    record: SourceRecord,
    rows: list[Any],
    detail: str,
) -> SourceRun:
    """Upsert mapped rows as ontology objects. Skips non-dict rows."""
    type_def = store.ontology.object_type(record.object_type)
    primary_key = type_def.primary_key
    upserted: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        props = mapped_properties(row, record, primary_key)
        if not props:
            continue
        obj = store.upsert_object(record.object_type, props, source="funnel")
        upserted.append(
            {"type": obj.object_type, "id": obj.id, "version": obj.version}
        )
    return SourceRun(upserted=upserted, detail=detail)


def fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> Any:
    """GET JSON from a URL. Never log headers."""
    if not url:
        raise ConnectorError("source needs a URL")
    try:
        response = httpx.get(url, headers=headers or {}, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise ConnectorError(f"could not read {url}: {exc}") from exc
