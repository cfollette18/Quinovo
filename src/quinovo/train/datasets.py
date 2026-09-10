"""Filtered sets: collect live kernel records into named datasets."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quinovo.apps.humanize import status_label, title_case
from quinovo.engine.store import AuditRow, InferredFact, ObjectStore, StoredLink, StoredObject
from quinovo.language.models import Ontology
from quinovo.train.filters import (
    COLLECT_CAP,
    FAMILIES,
    PREVIEW_DEFAULT,
    SNAPSHOT_CAP,
    ReviewGate,
    TrainError,
    TrainFamily,
    _in_window,
    _is_secret_key,
    _keep_status,
    _keep_type,
    _matches_query,
    _record,
)


def train_dir_for(db_path: Path) -> Path:
    return Path(db_path).parent / "train"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _object_title(store: ObjectStore, ontology: Ontology, object_type: str, pk: str) -> str:
    obj = store.get_object(object_type, pk)
    if obj is None:
        return pk
    try:
        title_prop = ontology.object_type(object_type).title_property
    except KeyError:
        title_prop = ""
    if title_prop:
        label = obj.properties.get(title_prop)
        if label:
            return str(label)
    for key in ("name", "title", "label", "display_name"):
        label = obj.properties.get(key)
        if label:
            return str(label)
    return pk


def _thing_record(
    ontology: Ontology,
    obj: StoredObject,
    include: list[str],
    exclude: list[str],
) -> dict[str, Any]:
    try:
        title_prop = ontology.object_type(obj.object_type).title_property
    except KeyError:
        title_prop = ""
    title = str(obj.properties.get(title_prop) or obj.id) if title_prop else obj.id
    kind = title_case(obj.object_type)
    details = [
        f"{title_case(key)}: {value}"
        for key, value in obj.properties.items()
        if key not in {title_prop, obj.id} and not _is_secret_key(key)
    ]
    extra = f" {details[0]}." if details else ""
    return _record(
        family="things",
        rec_id=f"thing:{obj.object_type}:{obj.id}",
        rec_type=obj.object_type,
        title=title,
        summary=f"{title} is a {kind.lower()}.{extra}",
        status_raw="asserted",
        when=None,
        fields={"kind": obj.object_type, "id": obj.id, **obj.properties},
        include=include,
        exclude=exclude,
    )


def _connection_record(
    store: ObjectStore,
    ontology: Ontology,
    link: StoredLink,
    include: list[str],
    exclude: list[str],
) -> dict[str, Any]:
    from_title = _object_title(store, ontology, link.from_type, link.from_id)
    to_title = _object_title(store, ontology, link.to_type, link.to_id)
    relation = title_case(link.link_type).lower()
    return _record(
        family="connections",
        rec_id=f"link:{link.link_type}:{link.from_type}:{link.from_id}:{link.to_type}:{link.to_id}",
        rec_type=link.link_type,
        title=f"{from_title} · {to_title}",
        summary=f"{from_title} {relation} {to_title}.",
        status_raw="asserted",
        when=None,
        fields={
            "from": f"{link.from_type}:{link.from_id}",
            "to": f"{link.to_type}:{link.to_id}",
            "from_name": from_title,
            "to_name": to_title,
            "connection": link.link_type,
        },
        include=include,
        exclude=exclude,
    )


def _noticed_record(
    store: ObjectStore,
    ontology: Ontology,
    fact: InferredFact,
    include: list[str],
    exclude: list[str],
) -> dict[str, Any]:
    title = _object_title(store, ontology, fact.object_type, fact.object_id)
    predicate = title_case(fact.predicate)
    return _record(
        family="noticed",
        rec_id=f"fact:{fact.id}",
        rec_type=fact.object_type,
        title=f"{title}: {predicate}",
        summary=f"Quinovo noticed {predicate.lower()} is {fact.value} for {title}.",
        status_raw=fact.status,
        when=fact.created_at,
        fields={
            "about": title,
            "noticed": fact.predicate,
            "value": fact.value,
            "rule": fact.rule,
            "confidence": fact.confidence,
        },
        include=include,
        exclude=exclude,
    )


def _changed_from_audit(row: AuditRow, include: list[str], exclude: list[str]) -> dict[str, Any]:
    action = title_case(row.action_type)
    result = status_label(row.result) or title_case(row.result)
    return _record(
        family="changed",
        rec_id=f"audit:{row.id}",
        rec_type=row.action_type,
        title=action,
        summary=f"{action} by {row.actor} · {result}.",
        status_raw=row.result,
        when=row.created_at,
        fields={"who": row.actor, "result": row.result, "when": row.created_at},
        include=include,
        exclude=exclude,
    )


def _changed_from_pending(
    action: dict[str, Any], include: list[str], exclude: list[str]
) -> dict[str, Any]:
    action_type = str(action.get("action_type") or "action")
    title = title_case(action_type)
    actor = action.get("actor") or "someone"
    return _record(
        family="changed",
        rec_id=f"pending:{action.get('id')}",
        rec_type=action_type,
        title=title,
        summary=f"{title} asked by {actor}.",
        status_raw=str(action.get("status") or "pending"),
        when=str(action.get("created_at") or "") or None,
        fields={"who": actor, "result": action.get("status")},
        include=include,
        exclude=exclude,
    )


def collect_records(ontology: Ontology, store: ObjectStore, filters: dict[str, Any]) -> list[dict[str, Any]]:
    kinds: list[TrainFamily] = list(filters.get("kinds") or FAMILIES)
    types: list[str] = list(filters.get("types") or [])
    gate: ReviewGate = filters.get("status") or "all"
    query = str(filters.get("q") or "")
    since = str(filters.get("since") or "")
    until = str(filters.get("until") or "")
    include = list(filters.get("include_fields") or [])
    exclude = list(filters.get("exclude_fields") or [])
    only_approved = bool(filters.get("only_approved"))

    found: list[dict[str, Any]] = []
    for family in kinds:
        match family:
            case "things":
                for type_def in ontology.object_types:
                    if types and type_def.api_name not in types:
                        continue
                    for obj in store.list_objects(type_def.api_name):
                        found.append(_thing_record(ontology, obj, include, exclude))
            case "connections":
                for link in store.list_all_links():
                    found.append(_connection_record(store, ontology, link, include, exclude))
            case "noticed":
                for fact in store.list_inferred_facts(status=None):
                    found.append(_noticed_record(store, ontology, fact, include, exclude))
            case "changed":
                for row in store.list_audit():
                    found.append(_changed_from_audit(row, include, exclude))
                for action in store.list_pending_actions():
                    found.append(_changed_from_pending(action, include, exclude))
            case _ as unreachable:
                raise AssertionError(f"unhandled family {unreachable}")

    kept: list[dict[str, Any]] = []
    for record in found:
        if record["family"] == "connections" and types:
            link_ok = record["type"] in types
            ends = (str(record["fields"].get("from") or ""), str(record["fields"].get("to") or ""))
            related = any(end.startswith(f"{item}:") for item in types for end in ends)
            if not (link_ok or related):
                continue
        elif not _keep_type(record, types):
            continue
        if not _keep_status(record, gate, only_approved):
            continue
        if not _in_window(record.get("when"), since, until):
            continue
        if not _matches_query(record, query):
            continue
        kept.append(record)
        if len(kept) >= COLLECT_CAP:
            break
    return kept


def preview_data(
    ontology: Ontology,
    store: ObjectStore,
    filters: dict[str, Any],
) -> dict[str, Any]:
    records = collect_records(ontology, store, filters)
    counts = {family: 0 for family in FAMILIES}
    for record in records:
        family = str(record["family"])
        if family in counts:
            counts[family] += 1
    limit = int(filters.get("limit") or PREVIEW_DEFAULT)
    shown = records[:limit]
    return {
        "filters": filters,
        "counts": {**counts, "total": len(records)},
        "shown": len(shown),
        "records": shown,
    }


def _read_list(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(key) if isinstance(payload, dict) else payload
    return list(rows or [])


def _write_list(path: Path, key: str, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: rows}, indent=2, default=str) + "\n", encoding="utf-8")


def list_datasets(root: Path) -> list[dict[str, Any]]:
    return _read_list(root / "datasets.json", "datasets")


def get_dataset(root: Path, dataset_id: str) -> dict[str, Any] | None:
    return next((row for row in list_datasets(root) if row.get("id") == dataset_id), None)


def example_from_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields") or {}
    lines = [f"{title_case(str(key))}: {value}" for key, value in fields.items()]
    body = "\n".join(lines) if lines else str(record.get("summary") or "")
    return {
        "instruction": (
            "You are a small specialist for this workspace. "
            "Restate the record in one plain sentence."
        ),
        "input": f"{record.get('family_label')}. {record.get('title')}.\n{body}",
        "output": record.get("summary") or record.get("title") or "",
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(example_from_record(record), ensure_ascii=False) for record in records]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return path


def save_dataset(
    ontology: Ontology,
    store: ObjectStore,
    root: Path,
    name: str,
    filters: dict[str, Any],
) -> dict[str, Any]:
    label = name.strip()
    if not label:
        raise TrainError("Give this set a name.")
    records = collect_records(ontology, store, filters)[:SNAPSHOT_CAP]
    counts = {family: 0 for family in FAMILIES}
    for record in records:
        family = str(record["family"])
        if family in counts:
            counts[family] += 1
    dataset_id = _new_id("ds")
    export_rel = f"exports/{dataset_id}.jsonl"
    write_jsonl(root / export_rel, records)
    public_filters = {key: value for key, value in filters.items() if key != "limit"}
    dataset = {
        "id": dataset_id,
        "name": label,
        "created_at": _now(),
        "filters": public_filters,
        "record_count": len(records),
        "counts": counts,
        "jsonl_path": export_rel,
        "records": records,
    }
    rows = list_datasets(root)
    rows.append(dataset)
    _write_list(root / "datasets.json", "datasets", rows)
    return dataset


def public_dataset(dataset: dict[str, Any], *, include_records: bool = False) -> dict[str, Any]:
    payload = {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "created_at": dataset.get("created_at"),
        "filters": dataset.get("filters") or {},
        "record_count": dataset.get("record_count"),
        "counts": dataset.get("counts") or {},
        "jsonl_path": dataset.get("jsonl_path"),
    }
    if include_records:
        payload["records"] = dataset.get("records") or []
    return payload
