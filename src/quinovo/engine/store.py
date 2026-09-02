from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from quinovo.language.models import ObjectTypeDef, Ontology, PropertyType


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def coerce_property(prop_type: PropertyType, value: Any) -> Any:
    match prop_type:
        case "string":
            return str(value)
        case "integer":
            return int(value)
        case "number":
            return float(value)
        case "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in {"true", "1", "yes"}:
                    return True
                if lowered in {"false", "0", "no"}:
                    return False
            raise ValueError(f"cannot coerce {value!r} to boolean")
        case _ as unreachable:
            raise TypeError(f"unsupported property type: {unreachable}")


@dataclass(frozen=True)
class StoredObject:
    object_type: str
    primary_key: str
    properties: dict[str, Any]
    version: int


@dataclass(frozen=True)
class StoredLink:
    link_type: str
    from_type: str
    from_pk: str
    to_type: str
    to_pk: str


@dataclass(frozen=True)
class AuditRow:
    id: int
    action_type: str
    actor: str
    at: str
    parameters: dict[str, Any]
    result: str


@dataclass(frozen=True)
class Proposal:
    id: int
    kind: str
    payload: dict[str, Any]
    confidence: float
    status: str
    actor: str
    created_at: str
    resolved_at: str | None
    resolved_by: str | None


@dataclass(frozen=True)
class Forecast:
    id: int
    object_type: str
    pk: str
    metric: str
    horizon_hours: float
    point: float
    q10: float | None
    q90: float | None
    model: str
    confidence: float
    as_of: str


@dataclass(frozen=True)
class InferredFact:
    id: int
    object_type: str
    pk: str
    predicate: str
    value: str
    confidence: float
    rule: str
    provenance: str
    status: str
    created_at: str
    provenance_detail: dict


class ObjectStore:
    """Indexed objects + named links + action audit. SQLite for make dev."""

    def __init__(self, ontology: Ontology, db_path: str | Path) -> None:
        self.ontology = ontology
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._init()

    def close(self) -> None:
        self._conn.close()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS objects (
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    properties TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY (object_type, pk)
                );
                CREATE TABLE IF NOT EXISTS links (
                    link_type TEXT NOT NULL,
                    from_type TEXT NOT NULL,
                    from_pk TEXT NOT NULL,
                    to_type TEXT NOT NULL,
                    to_pk TEXT NOT NULL,
                    PRIMARY KEY (link_type, from_type, from_pk, to_type, to_pk)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    at TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schema_overlay (
                    api_name TEXT PRIMARY KEY,
                    definition TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT
                );
                CREATE TABLE IF NOT EXISTS forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    horizon_hours REAL NOT NULL,
                    point REAL NOT NULL,
                    q10 REAL,
                    q90 REAL,
                    model TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    as_of TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS inferred_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    rule TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    provenance_detail TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (object_type, pk, predicate, rule)
                );
                CREATE TABLE IF NOT EXISTS property_overlay (
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    property TEXT NOT NULL,
                    PRIMARY KEY (object_type, pk, property)
                );
                CREATE TABLE IF NOT EXISTS series_points (
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    value REAL NOT NULL,
                    PRIMARY KEY (object_type, pk, metric, ts)
                );
                CREATE TABLE IF NOT EXISTS fga_tuples (
                    user_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_pk TEXT NOT NULL,
                    PRIMARY KEY (user_id, relation, object_type, object_pk)
                );
                CREATE TABLE IF NOT EXISTS scenarios (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scenario_edits (
                    scenario_id TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    pk TEXT NOT NULL,
                    property TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (scenario_id, object_type, pk, property)
                );
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()
        self._load_schema_overlay()

    def upsert_object(
        self,
        object_type: str,
        properties: dict[str, Any],
        *,
        source: Literal["funnel", "action"] = "funnel",
    ) -> StoredObject:
        type_def = self.ontology.object_type(object_type)
        normalized = self._normalize(type_def, properties)
        pk = str(normalized[type_def.primary_key])
        existing = self.get_object(object_type, pk)
        match source:
            case "funnel":
                if existing is not None:
                    for key in self.overlay_properties(object_type, pk):
                        if key in existing.properties:
                            normalized[key] = existing.properties[key]
            case "action":
                pass
            case _ as unreachable:
                raise TypeError(f"unhandled upsert source: {unreachable}")
        version = 1 if existing is None else existing.version + 1
        payload = json.dumps(normalized, sort_keys=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO objects (object_type, pk, properties, version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(object_type, pk) DO UPDATE SET
                    properties = excluded.properties,
                    version = excluded.version
                """,
                (object_type, pk, payload, version),
            )
            self._conn.commit()
        return StoredObject(object_type, pk, normalized, version)

    def get_object(self, object_type: str, pk: str) -> StoredObject | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT object_type, pk, properties, version FROM objects WHERE object_type = ? AND pk = ?",
                (object_type, pk),
            ).fetchone()
        if row is None:
            return None
        return StoredObject(
            row["object_type"],
            row["pk"],
            json.loads(row["properties"]),
            row["version"],
        )

    def list_objects(self, object_type: str) -> list[StoredObject]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT object_type, pk, properties, version FROM objects WHERE object_type = ? ORDER BY pk",
                (object_type,),
            ).fetchall()
        return [
            StoredObject(r["object_type"], r["pk"], json.loads(r["properties"]), r["version"])
            for r in rows
        ]

    def add_link(
        self,
        link_type: str,
        from_type: str,
        from_pk: str,
        to_type: str,
        to_pk: str,
    ) -> None:
        spec = self.ontology.link_type(link_type)
        if spec.from_type != from_type or spec.to_type != to_type:
            raise ValueError(
                f"link {link_type} expects {spec.from_type}->{spec.to_type}, "
                f"got {from_type}->{to_type}"
            )
        if self.get_object(from_type, from_pk) is None:
            raise KeyError(f"missing {from_type}:{from_pk}")
        if self.get_object(to_type, to_pk) is None:
            raise KeyError(f"missing {to_type}:{to_pk}")
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO links (link_type, from_type, from_pk, to_type, to_pk)
                VALUES (?, ?, ?, ?, ?)
                """,
                (link_type, from_type, from_pk, to_type, to_pk),
            )
            self._conn.commit()

    def search_around(self, object_type: str, pk: str, side_name: str) -> list[StoredObject]:
        """Follow a named link from this object. side_name is from_name or to_name."""
        found: list[StoredObject] = []
        seen: set[tuple[str, str]] = set()
        for spec in self.ontology.link_types:
            rows: list[sqlite3.Row]
            if spec.from_type == object_type and spec.from_name == side_name:
                with self._lock:
                    rows = self._conn.execute(
                        """
                        SELECT to_type AS object_type, to_pk AS pk
                        FROM links
                        WHERE link_type = ? AND from_type = ? AND from_pk = ?
                        """,
                        (spec.api_name, object_type, pk),
                    ).fetchall()
            elif spec.to_type == object_type and spec.to_name == side_name:
                with self._lock:
                    rows = self._conn.execute(
                        """
                        SELECT from_type AS object_type, from_pk AS pk
                        FROM links
                        WHERE link_type = ? AND to_type = ? AND to_pk = ?
                        """,
                        (spec.api_name, object_type, pk),
                    ).fetchall()
            else:
                continue
            for row in rows:
                key = (row["object_type"], row["pk"])
                if key in seen:
                    continue
                obj = self.get_object(row["object_type"], row["pk"])
                if obj is None:
                    continue
                seen.add(key)
                found.append(obj)
        if not found and not any(
            (link.from_type == object_type and link.from_name == side_name)
            or (link.to_type == object_type and link.to_name == side_name)
            for link in self.ontology.link_types
        ):
            raise KeyError(f"no link side {side_name!r} on {object_type}")
        return found

    def append_audit(
        self,
        action_type: str,
        actor: str,
        parameters: dict[str, Any],
        result: str,
    ) -> AuditRow:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO audit (action_type, actor, at, parameters, result)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, actor, _now(), json.dumps(parameters, sort_keys=True), result),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
            stored = self._conn.execute(
                "SELECT id, action_type, actor, at, parameters, result FROM audit WHERE id = ?",
                (row_id,),
            ).fetchone()
        return AuditRow(
            stored["id"],
            stored["action_type"],
            stored["actor"],
            stored["at"],
            json.loads(stored["parameters"]),
            stored["result"],
        )

    def list_audit(self) -> list[AuditRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, action_type, actor, at, parameters, result FROM audit ORDER BY id"
            ).fetchall()
        return [
            AuditRow(
                r["id"],
                r["action_type"],
                r["actor"],
                r["at"],
                json.loads(r["parameters"]),
                r["result"],
            )
            for r in rows
        ]

    def _normalize(self, type_def: ObjectTypeDef, properties: dict[str, Any]) -> dict[str, Any]:
        known = {p.api_name: p for p in type_def.properties}
        extra = set(properties) - set(known)
        if extra:
            raise ValueError(f"{type_def.api_name}: unknown properties {sorted(extra)}")
        out: dict[str, Any] = {}
        for prop in type_def.properties:
            if prop.api_name not in properties:
                if prop.required:
                    raise ValueError(
                        f"{type_def.api_name}: missing required property {prop.api_name}"
                    )
                continue
            out[prop.api_name] = coerce_property(prop.type, properties[prop.api_name])
        return out

    def iter_object_types(self) -> Iterator[str]:
        yield from (item.api_name for item in self.ontology.object_types)

    def _load_schema_overlay(self) -> None:
        with self._lock:
            rows = self._conn.execute("SELECT definition FROM schema_overlay").fetchall()
        for row in rows:
            type_def = ObjectTypeDef.model_validate(json.loads(row["definition"]))
            try:
                self.ontology.object_type(type_def.api_name)
            except KeyError:
                self.ontology.object_types.append(type_def)

    def register_object_type(self, type_def: ObjectTypeDef) -> None:
        try:
            existing = self.ontology.object_type(type_def.api_name)
        except KeyError:
            existing = None
        if existing is None:
            self.ontology.object_types.append(type_def)
        definition = json.dumps(type_def.model_dump(), sort_keys=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO schema_overlay (api_name, definition)
                VALUES (?, ?)
                ON CONFLICT(api_name) DO UPDATE SET definition = excluded.definition
                """,
                (type_def.api_name, definition),
            )
            self._conn.commit()

    def insert_proposal(
        self,
        kind: str,
        payload: dict[str, Any],
        confidence: float,
        actor: str,
        status: str,
    ) -> Proposal:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO proposals (
                    kind, payload, confidence, status, actor, created_at,
                    resolved_at, resolved_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    json.dumps(payload, sort_keys=True),
                    confidence,
                    status,
                    actor,
                    _now(),
                    _now() if status != "pending" else None,
                    actor if status != "pending" else None,
                ),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
        loaded = self.get_proposal(row_id)
        if loaded is None:
            raise RuntimeError("proposal insert failed")
        return loaded

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, kind, payload, confidence, status, actor,
                       created_at, resolved_at, resolved_by
                FROM proposals WHERE id = ?
                """,
                (proposal_id,),
            ).fetchone()
        return None if row is None else _proposal_from_row(row)

    def list_proposals(self, status: str | None = None) -> list[Proposal]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    """
                    SELECT id, kind, payload, confidence, status, actor,
                           created_at, resolved_at, resolved_by
                    FROM proposals ORDER BY id
                    """
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT id, kind, payload, confidence, status, actor,
                           created_at, resolved_at, resolved_by
                    FROM proposals WHERE status = ? ORDER BY id
                    """,
                    (status,),
                ).fetchall()
        return [_proposal_from_row(r) for r in rows]

    def set_proposal_status(
        self,
        proposal_id: int,
        status: str,
        resolved_by: str,
    ) -> Proposal:
        with self._lock:
            self._conn.execute(
                """
                UPDATE proposals
                SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE id = ?
                """,
                (status, _now(), resolved_by, proposal_id),
            )
            self._conn.commit()
        loaded = self.get_proposal(proposal_id)
        if loaded is None:
            raise KeyError(proposal_id)
        return loaded

    def put_forecast(
        self,
        object_type: str,
        pk: str,
        metric: str,
        horizon_hours: float,
        point: float,
        model: str,
        confidence: float,
        q10: float | None = None,
        q90: float | None = None,
    ) -> Forecast:
        if self.get_object(object_type, pk) is None:
            raise KeyError(f"missing {object_type}:{pk}")
        as_of = _now()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO forecasts (
                    object_type, pk, metric, horizon_hours, point, q10, q90,
                    model, confidence, as_of
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_type,
                    pk,
                    metric,
                    horizon_hours,
                    point,
                    q10,
                    q90,
                    model,
                    confidence,
                    as_of,
                ),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
        loaded = self.get_forecast(row_id)
        if loaded is None:
            raise RuntimeError("forecast insert failed")
        return loaded

    def get_forecast(self, forecast_id: int) -> Forecast | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, pk, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts WHERE id = ?
                """,
                (forecast_id,),
            ).fetchone()
        return None if row is None else _forecast_from_row(row)

    def list_forecasts(self, object_type: str, pk: str) -> list[Forecast]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, object_type, pk, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts
                WHERE object_type = ? AND pk = ?
                ORDER BY id
                """,
                (object_type, pk),
            ).fetchall()
        return [_forecast_from_row(r) for r in rows]

    def latest_forecast(self, object_type: str, pk: str, metric: str) -> Forecast | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, pk, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts
                WHERE object_type = ? AND pk = ? AND metric = ?
                ORDER BY id DESC LIMIT 1
                """,
                (object_type, pk, metric),
            ).fetchone()
        return None if row is None else _forecast_from_row(row)

    def upsert_inferred_fact(
        self,
        object_type: str,
        pk: str,
        predicate: str,
        value: str,
        confidence: float,
        rule: str,
        provenance: str,
        status: str,
        provenance_detail: dict[str, Any] | None = None,
    ) -> InferredFact:
        created = _now()
        detail = json.dumps(provenance_detail or {}, sort_keys=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO inferred_facts (
                    object_type, pk, predicate, value, confidence, rule,
                    provenance, provenance_detail, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_type, pk, predicate, rule) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    provenance = excluded.provenance,
                    provenance_detail = excluded.provenance_detail,
                    status = excluded.status,
                    created_at = excluded.created_at
                """,
                (
                    object_type,
                    pk,
                    predicate,
                    value,
                    confidence,
                    rule,
                    provenance,
                    detail,
                    status,
                    created,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                """
                SELECT id, object_type, pk, predicate, value, confidence, rule,
                       provenance, provenance_detail, status, created_at
                FROM inferred_facts
                WHERE object_type = ? AND pk = ? AND predicate = ? AND rule = ?
                """,
                (object_type, pk, predicate, rule),
            ).fetchone()
        return _inferred_from_row(row)

    def get_inferred_fact(self, fact_id: int) -> InferredFact | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, pk, predicate, value, confidence, rule,
                       provenance, provenance_detail, status, created_at
                FROM inferred_facts WHERE id = ?
                """,
                (fact_id,),
            ).fetchone()
        return None if row is None else _inferred_from_row(row)

    def list_inferred_facts(
        self,
        object_type: str | None = None,
        pk: str | None = None,
        status: str | None = None,
    ) -> list[InferredFact]:
        sql = """
            SELECT id, object_type, pk, predicate, value, confidence, rule,
                   provenance, provenance_detail, status, created_at
            FROM inferred_facts WHERE 1=1
        """
        params: list[Any] = []
        if object_type is not None:
            sql += " AND object_type = ?"
            params.append(object_type)
        if pk is not None:
            sql += " AND pk = ?"
            params.append(pk)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_inferred_from_row(r) for r in rows]

    def set_inferred_fact_status(self, fact_id: int, status: str) -> InferredFact:
        with self._lock:
            self._conn.execute(
                "UPDATE inferred_facts SET status = ? WHERE id = ?",
                (status, fact_id),
            )
            self._conn.commit()
        loaded = self.get_inferred_fact(fact_id)
        if loaded is None:
            raise KeyError(fact_id)
        return loaded

    def has_link(
        self,
        link_type: str,
        from_type: str,
        from_pk: str,
        to_type: str,
        to_pk: str,
    ) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM links
                WHERE link_type = ? AND from_type = ? AND from_pk = ?
                  AND to_type = ? AND to_pk = ?
                """,
                (link_type, from_type, from_pk, to_type, to_pk),
            ).fetchone()
        return row is not None

    def overlay_properties(self, object_type: str, pk: str) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT property FROM property_overlay
                WHERE object_type = ? AND pk = ?
                """,
                (object_type, pk),
            ).fetchall()
        return {row["property"] for row in rows}

    def mark_overlay(self, object_type: str, pk: str, properties: list[str]) -> None:
        with self._lock:
            for name in properties:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO property_overlay (object_type, pk, property)
                    VALUES (?, ?, ?)
                    """,
                    (object_type, pk, name),
                )
            self._conn.commit()


    def delete_object(self, object_type: str, pk: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM objects WHERE object_type = ? AND pk = ?",
                (object_type, pk),
            )
            self._conn.execute(
                "DELETE FROM links WHERE (from_type = ? AND from_pk = ?) OR (to_type = ? AND to_pk = ?)",
                (object_type, pk, object_type, pk),
            )
            self._conn.commit()

    def filter_objects(
        self,
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> list[StoredObject]:
        found = self.list_objects(object_type)
        if property_name is None:
            return found
        out: list[StoredObject] = []
        for obj in found:
            value = obj.properties.get(property_name)
            if equals is None and value is not None:
                out.append(obj)
            elif str(value) == equals:
                out.append(obj)
        return out

    def append_series_point(
        self, object_type: str, pk: str, metric: str, ts: str, value: float
    ) -> None:
        if self.get_object(object_type, pk) is None:
            raise KeyError(f"missing {object_type}:{pk}")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO series_points (object_type, pk, metric, ts, value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(object_type, pk, metric, ts) DO UPDATE SET value = excluded.value
                """,
                (object_type, pk, metric, ts, value),
            )
            self._conn.commit()

    def series_window(
        self, object_type: str, pk: str, metric: str, limit: int = 64
    ) -> list[tuple[str, float]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, value FROM series_points
                WHERE object_type = ? AND pk = ? AND metric = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (object_type, pk, metric, limit),
            ).fetchall()
        return [(row["ts"], float(row["value"])) for row in reversed(rows)]

    def list_series_metrics(self, object_type: str, pk: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT DISTINCT metric FROM series_points
                WHERE object_type = ? AND pk = ?
                ORDER BY metric
                """,
                (object_type, pk),
            ).fetchall()
        return [row["metric"] for row in rows]

    def write_tuple(self, user_id: str, relation: str, object_type: str, object_pk: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO fga_tuples (user_id, relation, object_type, object_pk)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, relation, object_type, object_pk),
            )
            self._conn.commit()

    def has_tuple(self, user_id: str, relation: str, object_type: str, object_pk: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM fga_tuples
                WHERE user_id = ? AND relation = ? AND object_type = ? AND object_pk = ?
                """,
                (user_id, relation, object_type, object_pk),
            ).fetchone()
        return row is not None

    def create_scenario(self, scenario_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO scenarios (id, status, created_at) VALUES (?, ?, ?)",
                (scenario_id, "open", _now()),
            )
            self._conn.commit()

    def scenario_set(
        self, scenario_id: str, object_type: str, pk: str, property_name: str, value: str
    ) -> None:
        self.create_scenario(scenario_id)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scenario_edits (scenario_id, object_type, pk, property, value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id, object_type, pk, property) DO UPDATE SET
                    value = excluded.value
                """,
                (scenario_id, object_type, pk, property_name, value),
            )
            self._conn.commit()

    def scenario_overlay(self, scenario_id: str, object_type: str, pk: str) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT property, value FROM scenario_edits
                WHERE scenario_id = ? AND object_type = ? AND pk = ?
                """,
                (scenario_id, object_type, pk),
            ).fetchall()
        return {row["property"]: row["value"] for row in rows}

    def apply_scenario(self, scenario_id: str) -> list[StoredObject]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT object_type, pk, property, value FROM scenario_edits
                WHERE scenario_id = ?
                """,
                (scenario_id,),
            ).fetchall()
        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (row["object_type"], row["pk"])
            grouped.setdefault(key, {})[row["property"]] = row["value"]
        edited: list[StoredObject] = []
        for (object_type, pk), props in grouped.items():
            obj = self.get_object(object_type, pk)
            if obj is None:
                continue
            merged = dict(obj.properties)
            merged.update(props)
            updated = self.upsert_object(object_type, merged, source="action")
            self.mark_overlay(object_type, pk, list(props))
            edited.append(updated)
        with self._lock:
            self._conn.execute(
                "UPDATE scenarios SET status = ? WHERE id = ?",
                ("applied", scenario_id),
            )
            self._conn.commit()
        return edited

    def enqueue_action(self, action_type: str, actor: str, parameters: dict[str, Any]) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO pending_actions (action_type, actor, parameters, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, actor, json.dumps(parameters, sort_keys=True), "pending", _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def list_pending_actions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, action_type, actor, parameters, status, created_at
                FROM pending_actions ORDER BY id
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "action_type": row["action_type"],
                "actor": row["actor"],
                "parameters": json.loads(row["parameters"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def set_pending_action_status(self, action_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE pending_actions SET status = ? WHERE id = ?",
                (status, action_id),
            )
            self._conn.commit()


def _proposal_from_row(row: sqlite3.Row) -> Proposal:
    return Proposal(
        row["id"],
        row["kind"],
        json.loads(row["payload"]),
        float(row["confidence"]),
        row["status"],
        row["actor"],
        row["created_at"],
        row["resolved_at"],
        row["resolved_by"],
    )


def _forecast_from_row(row: sqlite3.Row) -> Forecast:
    return Forecast(
        row["id"],
        row["object_type"],
        row["pk"],
        row["metric"],
        float(row["horizon_hours"]),
        float(row["point"]),
        None if row["q10"] is None else float(row["q10"]),
        None if row["q90"] is None else float(row["q90"]),
        row["model"],
        float(row["confidence"]),
        row["as_of"],
    )


def _inferred_from_row(row: sqlite3.Row) -> InferredFact:
    keys = row.keys()
    raw_detail = row["provenance_detail"] if "provenance_detail" in keys else "{}"
    try:
        detail = json.loads(raw_detail or "{}")
    except json.JSONDecodeError:
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    return InferredFact(
        row["id"],
        row["object_type"],
        row["pk"],
        row["predicate"],
        row["value"],
        float(row["confidence"]),
        row["rule"],
        row["provenance"],
        row["status"],
        row["created_at"],
        detail,
    )
