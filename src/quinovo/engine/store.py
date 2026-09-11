from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from quinovo.language.models import ObjectTypeDef, Ontology, PropertyType


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    id: str
    properties: dict[str, Any]
    version: int

    @property
    def primary_key(self) -> str:
        return self.id


@dataclass(frozen=True)
class StoredLink:
    link_type: str
    from_type: str
    from_id: str
    to_type: str
    to_id: str

    @property
    def from_pk(self) -> str:
        return self.from_id

    @property
    def to_pk(self) -> str:
        return self.to_id


@dataclass(frozen=True)
class AuditRow:
    id: int
    action_type: str
    actor: str
    created_at: str
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
    object_id: str
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
    object_id: str
    predicate: str
    value: str
    confidence: float
    rule: str
    provenance: str
    status: str
    created_at: str
    provenance_detail: dict


@dataclass(frozen=True)
class PendingAction:
    id: int
    action_type: str
    actor: str
    parameters: dict[str, Any]
    status: str
    created_at: str
    resolved_at: str | None
    resolved_by: str | None


@dataclass(frozen=True)
class SourceRecord:
    """One registered data source. Persisted in the store's sources table."""

    name: str
    kind: str
    object_type: str
    config: dict[str, Any]
    auto: bool = False
    description: str = ""
    created_at: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class SourceRunRecord:
    id: int
    source_name: str
    created_at: str
    upserted: int
    status: str
    detail: str


@dataclass(frozen=True)
class LogicSourceRecord:
    """One registered external logic source. Persisted in logic_sources."""

    name: str
    kind: str
    config: dict[str, Any]
    auto: bool = False
    description: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class ActionTargetRecord:
    """One write-back target bound to an action type."""

    action_type: str
    kind: str
    config: dict[str, Any]
    description: str = ""
    created_at: str = ""
    enabled: bool = True


SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    object_type TEXT NOT NULL,
    id TEXT NOT NULL,
    properties TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (object_type, id)
);
CREATE TABLE IF NOT EXISTS links (
    link_type TEXT NOT NULL,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    PRIMARY KEY (link_type, from_type, from_id, to_type, to_id)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
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
    object_id TEXT NOT NULL,
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
    object_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL,
    rule TEXT NOT NULL,
    provenance TEXT NOT NULL,
    provenance_detail TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (object_type, object_id, predicate, rule)
);
CREATE TABLE IF NOT EXISTS property_overlay (
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    property TEXT NOT NULL,
    PRIMARY KEY (object_type, object_id, property)
);
CREATE TABLE IF NOT EXISTS series_points (
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    ts TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (object_type, object_id, metric, ts)
);
CREATE TABLE IF NOT EXISTS fga_tuples (
    user_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    PRIMARY KEY (user_id, relation, object_type, object_id)
);
CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenario_edits (
    scenario_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    property TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (scenario_id, object_type, object_id, property)
);
CREATE TABLE IF NOT EXISTS pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    parameters TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    object_type TEXT NOT NULL,
    config TEXT NOT NULL,
    auto INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    upserted INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS logic_sources (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    config TEXT NOT NULL,
    auto INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_targets (
    action_type TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    config TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    object_type TEXT,
    object_id TEXT,
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS hooks (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    config TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS forecast_accuracy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    model TEXT NOT NULL,
    forecast_id INTEGER,
    horizon_hours REAL,
    point REAL,
    actual REAL,
    abs_pct_error REAL,
    covered INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_links_to ON links (link_type, to_type, to_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_latest
    ON forecasts (object_type, object_id, metric, id DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals (status);
CREATE INDEX IF NOT EXISTS idx_inferred_facts_status ON inferred_facts (status);
"""

# Migration 1: pre-versioning schema → conventions naming (docs/conventions.md).
_RENAMES: dict[str, tuple[tuple[str, str], ...]] = {
    "objects": (("pk", "id"),),
    "links": (("from_pk", "from_id"), ("to_pk", "to_id")),
    "forecasts": (("pk", "object_id"),),
    "inferred_facts": (("pk", "object_id"),),
    "property_overlay": (("pk", "object_id"),),
    "series_points": (("pk", "object_id"),),
    "scenario_edits": (("pk", "object_id"),),
    "fga_tuples": (("object_pk", "object_id"),),
    "audit": (("at", "created_at"),),
    "source_runs": (("at", "created_at"),),
    "sources": (("auto_pull", "auto"),),
    "logic_sources": (("auto_run", "auto"),),
}


class ObjectStore:
    """Indexed objects + named links + action audit. SQLite for make dev."""

    def __init__(self, ontology: Ontology, db_path: str | Path) -> None:
        self.ontology = ontology
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.on_index_change: Callable[[], None] | None = None
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._init()

    def _note_index_change(self) -> None:
        cb = self.on_index_change
        if cb is not None:
            cb()

    def index_fingerprint(self) -> str:
        """Object count, versions, last write, and a hash of live ids."""
        with self._lock:
            obj_n, obj_ver = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(version), 0) FROM objects"
            ).fetchone()
            link_n = self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            series_n = self._conn.execute("SELECT COUNT(*) FROM series_points").fetchone()[0]
            forecast_n = self._conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
            ids = self._conn.execute(
                "SELECT object_type, id FROM objects ORDER BY object_type, id"
            ).fetchall()
        raw = f"{obj_n}:{obj_ver}:{link_n}:{series_n}:{forecast_n}:"
        raw += ";".join(f"{row[0]}:{row[1]}" for row in ids)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def close(self) -> None:
        self._conn.close()

    def _init(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            has_objects = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'objects'"
            ).fetchone()
            if version == 0 and has_objects is not None:
                self._migrate_1()
                version = 1
            self._conn.executescript(_SCHEMA)
            self._ensure_column("pending_actions", "resolved_at", "TEXT")
            self._ensure_column("pending_actions", "resolved_by", "TEXT")
            self._ensure_column("sources", "enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column("action_targets", "enabled", "INTEGER NOT NULL DEFAULT 1")
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()
        self._load_schema_overlay()

    def _migrate_1(self) -> None:
        """Rename pre-conventions columns; RENAME COLUMN, table-rebuild fallback."""
        for table, pairs in _RENAMES.items():
            for old, new in pairs:
                self._rename_column(table, old, new)

    def _rename_column(self, table: str, old: str, new: str) -> None:
        exists = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if exists is None:
            return
        names = {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")}
        if old not in names or new in names:
            return
        try:
            self._conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
        except sqlite3.OperationalError:
            self._rebuild_renamed(table, old, new)

    def _rebuild_renamed(self, table: str, old: str, new: str) -> None:
        """Fallback for SQLite without RENAME COLUMN (< 3.25): rebuild the table."""
        info = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk_cols = [r[1] for r in sorted((r for r in info if r[4]), key=lambda r: r[4])]
        defs: list[str] = []
        for name, col_type, not_null, default, pk in info:
            renamed = new if name == old else name
            line = f"{renamed} {col_type or 'TEXT'}"
            if pk and len(pk_cols) == 1:
                line += " PRIMARY KEY"
                if (col_type or "").upper() == "INTEGER":
                    line += " AUTOINCREMENT"
            if not_null:
                line += " NOT NULL"
            if default is not None:
                line += f" DEFAULT {default}"
            defs.append(line)
        if len(pk_cols) > 1:
            defs.append(
                "PRIMARY KEY (" + ", ".join(new if c == old else c for c in pk_cols) + ")"
            )
        old_names = ", ".join(r[1] for r in info)
        new_names = ", ".join(new if r[1] == old else r[1] for r in info)
        self._conn.execute(f"ALTER TABLE {table} RENAME TO {table}__pre_v1")
        self._conn.execute(f"CREATE TABLE {table} ({', '.join(defs)})")
        self._conn.execute(
            f"INSERT INTO {table} ({new_names}) SELECT {old_names} FROM {table}__pre_v1"
        )
        self._conn.execute(f"DROP TABLE {table}__pre_v1")

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        names = {row[1] for row in rows}
        if column not in names:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def upsert_object(
        self,
        object_type: str,
        properties: dict[str, Any],
        *,
        source: Literal["funnel", "action"] = "funnel",
    ) -> StoredObject:
        type_def = self.ontology.object_type(object_type)
        normalized = self._normalize(type_def, properties)
        object_id = str(normalized[type_def.primary_key])
        existing = self.get_object(object_type, object_id)
        match source:
            case "funnel":
                if existing is not None:
                    for key in self.overlay_properties(object_type, object_id):
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
                INSERT INTO objects (object_type, id, properties, version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(object_type, id) DO UPDATE SET
                    properties = excluded.properties,
                    version = excluded.version
                """,
                (object_type, object_id, payload, version),
            )
            self._conn.commit()
        self._note_index_change()
        return StoredObject(object_type, object_id, normalized, version)

    def get_object(self, object_type: str, id: str) -> StoredObject | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT object_type, id, properties, version FROM objects WHERE object_type = ? AND id = ?",
                (object_type, id),
            ).fetchone()
        if row is None:
            return None
        return StoredObject(
            row["object_type"],
            row["id"],
            json.loads(row["properties"]),
            row["version"],
        )

    def list_objects(self, object_type: str) -> list[StoredObject]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT object_type, id, properties, version FROM objects WHERE object_type = ? ORDER BY id",
                (object_type,),
            ).fetchall()
        return [
            StoredObject(r["object_type"], r["id"], json.loads(r["properties"]), r["version"])
            for r in rows
        ]

    def add_link(
        self,
        link_type: str,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
    ) -> None:
        spec = self.ontology.link_type(link_type)
        if spec.from_type != from_type or spec.to_type != to_type:
            raise ValueError(
                f"link {link_type} expects {spec.from_type}->{spec.to_type}, "
                f"got {from_type}->{to_type}"
            )
        if self.get_object(from_type, from_id) is None:
            raise KeyError(f"missing {from_type}:{from_id}")
        if self.get_object(to_type, to_id) is None:
            raise KeyError(f"missing {to_type}:{to_id}")
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO links (link_type, from_type, from_id, to_type, to_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (link_type, from_type, from_id, to_type, to_id),
            )
            self._conn.commit()
        self._note_index_change()

    def search_around(self, object_type: str, id: str, side_name: str) -> list[StoredObject]:
        """Follow a named link from this object. side_name is from_name or to_name."""
        found: list[StoredObject] = []
        seen: set[tuple[str, str]] = set()
        for spec in self.ontology.link_types:
            rows: list[sqlite3.Row]
            if spec.from_type == object_type and spec.from_name == side_name:
                with self._lock:
                    rows = self._conn.execute(
                        """
                        SELECT to_type AS object_type, to_id AS id
                        FROM links
                        WHERE link_type = ? AND from_type = ? AND from_id = ?
                        """,
                        (spec.api_name, object_type, id),
                    ).fetchall()
            elif spec.to_type == object_type and spec.to_name == side_name:
                with self._lock:
                    rows = self._conn.execute(
                        """
                        SELECT from_type AS object_type, from_id AS id
                        FROM links
                        WHERE link_type = ? AND to_type = ? AND to_id = ?
                        """,
                        (spec.api_name, object_type, id),
                    ).fetchall()
            else:
                continue
            for row in rows:
                key = (row["object_type"], row["id"])
                if key in seen:
                    continue
                obj = self.get_object(row["object_type"], row["id"])
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

    def list_all_links(self) -> list[StoredLink]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT link_type, from_type, from_id, to_type, to_id
                FROM links
                """
            ).fetchall()
        return [
            StoredLink(
                row["link_type"],
                row["from_type"],
                row["from_id"],
                row["to_type"],
                row["to_id"],
            )
            for row in rows
        ]

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
                INSERT INTO audit (action_type, actor, created_at, parameters, result)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, actor, _now(), json.dumps(parameters, sort_keys=True), result),
            )
            self._conn.commit()
            row_id = int(cur.lastrowid or 0)
            stored = self._conn.execute(
                "SELECT id, action_type, actor, created_at, parameters, result FROM audit WHERE id = ?",
                (row_id,),
            ).fetchone()
        return AuditRow(
            stored["id"],
            stored["action_type"],
            stored["actor"],
            stored["created_at"],
            json.loads(stored["parameters"]),
            stored["result"],
        )

    def list_audit(self) -> list[AuditRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, action_type, actor, created_at, parameters, result FROM audit ORDER BY id"
            ).fetchall()
        return [
            AuditRow(
                r["id"],
                r["action_type"],
                r["actor"],
                r["created_at"],
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
        id: str,
        metric: str,
        horizon_hours: float,
        point: float,
        model: str,
        confidence: float,
        q10: float | None = None,
        q90: float | None = None,
    ) -> Forecast:
        if self.get_object(object_type, id) is None:
            raise KeyError(f"missing {object_type}:{id}")
        as_of = _now()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO forecasts (
                    object_type, object_id, metric, horizon_hours, point, q10, q90,
                    model, confidence, as_of
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_type,
                    id,
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
        self._note_index_change()
        return loaded

    def get_forecast(self, forecast_id: int) -> Forecast | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, object_id, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts WHERE id = ?
                """,
                (forecast_id,),
            ).fetchone()
        return None if row is None else _forecast_from_row(row)

    def list_forecasts(self, object_type: str, id: str) -> list[Forecast]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, object_type, object_id, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts
                WHERE object_type = ? AND object_id = ?
                ORDER BY id
                """,
                (object_type, id),
            ).fetchall()
        return [_forecast_from_row(r) for r in rows]

    def latest_forecast(self, object_type: str, id: str, metric: str) -> Forecast | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, object_id, metric, horizon_hours, point, q10, q90,
                       model, confidence, as_of
                FROM forecasts
                WHERE object_type = ? AND object_id = ? AND metric = ?
                ORDER BY id DESC LIMIT 1
                """,
                (object_type, id, metric),
            ).fetchone()
        return None if row is None else _forecast_from_row(row)

    def upsert_inferred_fact(
        self,
        object_type: str,
        id: str,
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
                    object_type, object_id, predicate, value, confidence, rule,
                    provenance, provenance_detail, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(object_type, object_id, predicate, rule) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    provenance = excluded.provenance,
                    provenance_detail = excluded.provenance_detail,
                    status = excluded.status,
                    created_at = excluded.created_at
                """,
                (
                    object_type,
                    id,
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
                SELECT id, object_type, object_id, predicate, value, confidence, rule,
                       provenance, provenance_detail, status, created_at
                FROM inferred_facts
                WHERE object_type = ? AND object_id = ? AND predicate = ? AND rule = ?
                """,
                (object_type, id, predicate, rule),
            ).fetchone()
        return _inferred_from_row(row)

    def get_inferred_fact(self, fact_id: int) -> InferredFact | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, object_type, object_id, predicate, value, confidence, rule,
                       provenance, provenance_detail, status, created_at
                FROM inferred_facts WHERE id = ?
                """,
                (fact_id,),
            ).fetchone()
        return None if row is None else _inferred_from_row(row)

    def list_inferred_facts(
        self,
        object_type: str | None = None,
        id: str | None = None,
        status: str | None = None,
    ) -> list[InferredFact]:
        sql = """
            SELECT id, object_type, object_id, predicate, value, confidence, rule,
                   provenance, provenance_detail, status, created_at
            FROM inferred_facts WHERE 1=1
        """
        params: list[Any] = []
        if object_type is not None:
            sql += " AND object_type = ?"
            params.append(object_type)
        if id is not None:
            sql += " AND object_id = ?"
            params.append(id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_inferred_from_row(r) for r in rows]

    def list_inferred_rules(self) -> dict[str, int]:
        """Rule name -> how many inferred facts it left behind."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT rule, COUNT(*) AS n FROM inferred_facts GROUP BY rule"
            ).fetchall()
        return {str(row["rule"]): int(row["n"]) for row in rows}

    def delete_inferred_facts_by_rule(self, rule: str) -> int:
        """Forget every fact a rule produced (used when the rule itself is gone)."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM inferred_facts WHERE rule = ?", (rule,))
            self._conn.commit()
            deleted = int(cursor.rowcount or 0)
        if deleted:
            self._note_index_change()
        return deleted

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
        from_id: str,
        to_type: str,
        to_id: str,
    ) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM links
                WHERE link_type = ? AND from_type = ? AND from_id = ?
                  AND to_type = ? AND to_id = ?
                """,
                (link_type, from_type, from_id, to_type, to_id),
            ).fetchone()
        return row is not None

    def overlay_properties(self, object_type: str, id: str) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT property FROM property_overlay
                WHERE object_type = ? AND object_id = ?
                """,
                (object_type, id),
            ).fetchall()
        return {row["property"] for row in rows}

    def mark_overlay(self, object_type: str, id: str, properties: list[str]) -> None:
        with self._lock:
            for name in properties:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO property_overlay (object_type, object_id, property)
                    VALUES (?, ?, ?)
                    """,
                    (object_type, id, name),
                )
            self._conn.commit()


    def delete_object(self, object_type: str, id: str) -> None:
        """Delete an object and everything the store holds about it."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM objects WHERE object_type = ? AND id = ?",
                (object_type, id),
            )
            self._conn.execute(
                "DELETE FROM links WHERE (from_type = ? AND from_id = ?) OR (to_type = ? AND to_id = ?)",
                (object_type, id, object_type, id),
            )
            for table in (
                "forecasts",
                "inferred_facts",
                "series_points",
                "property_overlay",
                "scenario_edits",
            ):
                self._conn.execute(
                    f"DELETE FROM {table} WHERE object_type = ? AND object_id = ?",
                    (object_type, id),
                )
            self._conn.commit()
        self._note_index_change()

    def filter_objects(
        self,
        object_type: str,
        property_name: str | None = None,
        equals: str | None = None,
    ) -> list[StoredObject]:
        sql = "SELECT object_type, id, properties, version FROM objects WHERE object_type = ?"
        params: list[Any] = [object_type]
        if property_name is not None:
            path = f'$."{property_name}"'
            if equals is None:
                sql += " AND json_extract(properties, ?) IS NOT NULL"
                params.append(path)
            else:
                sql += " AND CAST(json_extract(properties, ?) AS TEXT) = ?"
                params.extend([path, equals])
        sql += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            StoredObject(r["object_type"], r["id"], json.loads(r["properties"]), r["version"])
            for r in rows
        ]

    def append_series_point(
        self, object_type: str, id: str, metric: str, ts: str, value: float
    ) -> None:
        if self.get_object(object_type, id) is None:
            raise KeyError(f"missing {object_type}:{id}")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO series_points (object_type, object_id, metric, ts, value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(object_type, object_id, metric, ts) DO UPDATE SET value = excluded.value
                """,
                (object_type, id, metric, ts, value),
            )
            self._conn.commit()
        self._note_index_change()

    def series_window(
        self, object_type: str, id: str, metric: str, limit: int = 64
    ) -> list[tuple[str, float]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, value FROM series_points
                WHERE object_type = ? AND object_id = ? AND metric = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (object_type, id, metric, limit),
            ).fetchall()
        return [(row["ts"], float(row["value"])) for row in reversed(rows)]

    def list_series_metrics(self, object_type: str, id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT DISTINCT metric FROM series_points
                WHERE object_type = ? AND object_id = ?
                ORDER BY metric
                """,
                (object_type, id),
            ).fetchall()
        return [row["metric"] for row in rows]

    def write_tuple(self, user_id: str, relation: str, object_type: str, object_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO fga_tuples (user_id, relation, object_type, object_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, relation, object_type, object_id),
            )
            self._conn.commit()

    def has_tuple(self, user_id: str, relation: str, object_type: str, object_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1 FROM fga_tuples
                WHERE user_id = ? AND relation = ? AND object_type = ? AND object_id = ?
                """,
                (user_id, relation, object_type, object_id),
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
        self, scenario_id: str, object_type: str, id: str, property_name: str, value: str
    ) -> None:
        self.create_scenario(scenario_id)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scenario_edits (scenario_id, object_type, object_id, property, value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id, object_type, object_id, property) DO UPDATE SET
                    value = excluded.value
                """,
                (scenario_id, object_type, id, property_name, value),
            )
            self._conn.commit()

    def scenario_overlay(self, scenario_id: str, object_type: str, id: str) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT property, value FROM scenario_edits
                WHERE scenario_id = ? AND object_type = ? AND object_id = ?
                """,
                (scenario_id, object_type, id),
            ).fetchall()
        return {row["property"]: row["value"] for row in rows}

    def apply_scenario(self, scenario_id: str) -> list[StoredObject]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT object_type, object_id, property, value FROM scenario_edits
                WHERE scenario_id = ?
                """,
                (scenario_id,),
            ).fetchall()
        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for row in rows:
            key = (row["object_type"], row["object_id"])
            grouped.setdefault(key, {})[row["property"]] = row["value"]
        edited: list[StoredObject] = []
        for (object_type, object_id), props in grouped.items():
            obj = self.get_object(object_type, object_id)
            if obj is None:
                continue
            merged = dict(obj.properties)
            merged.update(props)
            updated = self.upsert_object(object_type, merged, source="action")
            self.mark_overlay(object_type, object_id, list(props))
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
                INSERT INTO pending_actions (
                    action_type, actor, parameters, status, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, actor, json.dumps(parameters, sort_keys=True), "pending", _now()),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def get_pending_action(self, action_id: int) -> PendingAction | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, action_type, actor, parameters, status, created_at,
                       resolved_at, resolved_by
                FROM pending_actions WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
        return None if row is None else _pending_action_from_row(row)

    def list_pending_actions(self, status: str | None = None) -> list[PendingAction]:
        sql = """
            SELECT id, action_type, actor, parameters, status, created_at,
                   resolved_at, resolved_by
            FROM pending_actions
        """
        params: list[Any] = []
        if status is not None:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_pending_action_from_row(r) for r in rows]

    def set_pending_action_status(
        self,
        action_id: int,
        status: str,
        resolved_by: str | None = None,
    ) -> PendingAction:
        with self._lock:
            if status == "pending":
                self._conn.execute(
                    "UPDATE pending_actions SET status = ? WHERE id = ?",
                    (status, action_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE pending_actions
                    SET status = ?, resolved_at = ?, resolved_by = ?
                    WHERE id = ?
                    """,
                    (status, _now(), resolved_by, action_id),
                )
            self._conn.commit()
        loaded = self.get_pending_action(action_id)
        if loaded is None:
            raise KeyError(action_id)
        return loaded

    # --- Data sources (connectors) -------------------------------------

    def upsert_source(
        self,
        name: str,
        kind: str,
        object_type: str,
        config: dict[str, Any],
        auto: bool = False,
        description: str = "",
        enabled: bool = True,
    ) -> SourceRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sources (name, kind, object_type, config, auto, description, created_at, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    kind = excluded.kind,
                    object_type = excluded.object_type,
                    config = excluded.config,
                    auto = excluded.auto,
                    description = excluded.description,
                    enabled = excluded.enabled
                """,
                (
                    name,
                    kind,
                    object_type,
                    json.dumps(config, sort_keys=True),
                    1 if auto else 0,
                    description,
                    _now(),
                    1 if enabled else 0,
                ),
            )
            self._conn.commit()
        loaded = self.get_source(name)
        if loaded is None:
            raise RuntimeError("source upsert failed")
        return loaded

    def get_source(self, name: str) -> SourceRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT name, kind, object_type, config, auto, description, created_at, enabled "
                "FROM sources WHERE name = ?",
                (name,),
            ).fetchone()
        return _source_from_row(row) if row is not None else None

    def list_sources(self) -> list[SourceRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, kind, object_type, config, auto, description, created_at, enabled "
                "FROM sources ORDER BY name"
            ).fetchall()
        return [_source_from_row(r) for r in rows]

    def delete_source(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sources WHERE name = ?", (name,))
            self._conn.commit()

    def record_source_run(
        self, source_name: str, upserted: int, status: str = "ok", detail: str = ""
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO source_runs (source_name, created_at, upserted, status, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_name, _now(), upserted, status, detail),
            )
            self._conn.commit()

    def list_source_runs(self, limit: int = 50) -> list[SourceRunRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, source_name, created_at, upserted, status, detail FROM source_runs "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_source_run_from_row(r) for r in rows]

    # --- External logic sources ---------------------------------------

    def upsert_logic_source(
        self,
        name: str,
        kind: str,
        config: dict[str, Any],
        auto: bool = False,
        description: str = "",
    ) -> LogicSourceRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO logic_sources (name, kind, config, auto, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    kind = excluded.kind,
                    config = excluded.config,
                    auto = excluded.auto,
                    description = excluded.description
                """,
                (
                    name,
                    kind,
                    json.dumps(config, sort_keys=True),
                    1 if auto else 0,
                    description,
                    _now(),
                ),
            )
            self._conn.commit()
        loaded = self.get_logic_source(name)
        if loaded is None:
            raise RuntimeError("logic source upsert failed")
        return loaded

    def get_logic_source(self, name: str) -> LogicSourceRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT name, kind, config, auto, description, created_at "
                "FROM logic_sources WHERE name = ?",
                (name,),
            ).fetchone()
        return _logic_source_from_row(row) if row is not None else None

    def list_logic_sources(self) -> list[LogicSourceRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, kind, config, auto, description, created_at "
                "FROM logic_sources ORDER BY name"
            ).fetchall()
        return [_logic_source_from_row(r) for r in rows]

    def delete_logic_source(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM logic_sources WHERE name = ?", (name,))
            self._conn.commit()

    # --- Action write-back targets -------------------------------------

    def upsert_action_target(
        self,
        action_type: str,
        kind: str,
        config: dict[str, Any],
        description: str = "",
        enabled: bool = True,
    ) -> ActionTargetRecord:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO action_targets (action_type, kind, config, description, created_at, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(action_type) DO UPDATE SET
                    kind = excluded.kind,
                    config = excluded.config,
                    description = excluded.description,
                    enabled = excluded.enabled
                """,
                (
                    action_type,
                    kind,
                    json.dumps(config, sort_keys=True),
                    description,
                    _now(),
                    1 if enabled else 0,
                ),
            )
            self._conn.commit()
        loaded = self.get_action_target(action_type)
        if loaded is None:
            raise RuntimeError("action target upsert failed")
        return loaded

    def get_action_target(self, action_type: str) -> ActionTargetRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT action_type, kind, config, description, created_at, enabled "
                "FROM action_targets WHERE action_type = ?",
                (action_type,),
            ).fetchone()
        return _action_target_from_row(row) if row is not None else None

    def list_action_targets(self) -> list[ActionTargetRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT action_type, kind, config, description, created_at, enabled "
                "FROM action_targets ORDER BY action_type"
            ).fetchall()
        return [_action_target_from_row(r) for r in rows]

    def delete_action_target(self, action_type: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM action_targets WHERE action_type = ?", (action_type,))
            self._conn.commit()

    def remove_link(
        self,
        link_type: str,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
    ) -> None:
        spec = self.ontology.link_type(link_type)
        if spec.from_type != from_type or spec.to_type != to_type:
            raise ValueError(
                f"link {link_type} expects {spec.from_type}->{spec.to_type}, "
                f"got {from_type}->{to_type}"
            )
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM links
                WHERE link_type = ? AND from_type = ? AND from_id = ?
                  AND to_type = ? AND to_id = ?
                """,
                (link_type, from_type, from_id, to_type, to_id),
            )
            self._conn.commit()
        self._note_index_change()


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
        row["object_id"],
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
    try:
        detail = json.loads(row["provenance_detail"] or "{}")
    except json.JSONDecodeError:
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    return InferredFact(
        row["id"],
        row["object_type"],
        row["object_id"],
        row["predicate"],
        row["value"],
        float(row["confidence"]),
        row["rule"],
        row["provenance"],
        row["status"],
        row["created_at"],
        detail,
    )


def _pending_action_from_row(row: sqlite3.Row) -> PendingAction:
    return PendingAction(
        row["id"],
        row["action_type"],
        row["actor"],
        json.loads(row["parameters"]),
        row["status"],
        row["created_at"],
        row["resolved_at"],
        row["resolved_by"],
    )


def _source_from_row(row: sqlite3.Row) -> SourceRecord:
    return SourceRecord(
        name=row["name"],
        kind=row["kind"],
        object_type=row["object_type"],
        config=json.loads(row["config"]),
        auto=bool(row["auto"]),
        description=row["description"],
        created_at=row["created_at"],
        enabled=bool(row["enabled"]),
    )


def _source_run_from_row(row: sqlite3.Row) -> SourceRunRecord:
    return SourceRunRecord(
        id=row["id"],
        source_name=row["source_name"],
        created_at=row["created_at"],
        upserted=int(row["upserted"]),
        status=row["status"],
        detail=row["detail"],
    )


def _logic_source_from_row(row: sqlite3.Row) -> LogicSourceRecord:
    return LogicSourceRecord(
        name=row["name"],
        kind=row["kind"],
        config=json.loads(row["config"]),
        auto=bool(row["auto"]),
        description=row["description"],
        created_at=row["created_at"],
    )


def _action_target_from_row(row: sqlite3.Row) -> ActionTargetRecord:
    return ActionTargetRecord(
        action_type=row["action_type"],
        kind=row["kind"],
        config=json.loads(row["config"]),
        description=row["description"],
        created_at=row["created_at"],
        enabled=bool(row["enabled"]),
    )


