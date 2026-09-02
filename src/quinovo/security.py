"""OpenFGA-shaped call-time security. Pack YAML, tuples in the store. No app filters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from quinovo.engine.store import ObjectStore, StoredObject


class SecurityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleDef(SecurityModel):
    types: list[str] = Field(default_factory=lambda: ["*"])
    actions: list[str] = Field(default_factory=list)
    unattended_actions: list[str] = Field(default_factory=list)
    row_link: dict[str, str] = Field(default_factory=dict)
    hide_properties: dict[str, list[str]] = Field(default_factory=dict)


class BindingDef(SecurityModel):
    role: str
    as_object: str | None = None


class SecurityPolicy(SecurityModel):
    roles: dict[str, RoleDef] = Field(default_factory=dict)
    bindings: dict[str, BindingDef] = Field(default_factory=dict)


class SecurityError(Exception):
    pass


def load_security(path: str | Path) -> SecurityPolicy:
    raw = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: security file must be a mapping")
    return SecurityPolicy.model_validate(data)


def seed_tuples(store: ObjectStore, policy: SecurityPolicy) -> None:
    for user, binding in policy.bindings.items():
        for object_type in store.ontology.object_types:
            store.write_tuple(user, binding.role, object_type.api_name, "*")


class Guard:
    def __init__(self, store: ObjectStore, policy: SecurityPolicy | None) -> None:
        self.store = store
        self.policy = policy

    def role_for(self, actor: str) -> tuple[str, RoleDef, str | None]:
        if self.policy is None:
            return "admin", RoleDef(types=["*"], actions=["*"]), None
        binding = self.policy.bindings.get(actor)
        if binding is None:
            raise SecurityError(f"unknown actor {actor!r}")
        role = self.policy.roles.get(binding.role)
        if role is None:
            raise SecurityError(f"unknown role {binding.role!r}")
        return binding.role, role, binding.as_object

    def can_read(self, actor: str, obj: StoredObject) -> bool:
        try:
            _name, role, as_object = self.role_for(actor)
        except SecurityError:
            return False
        if "*" not in role.types and obj.object_type not in role.types:
            return False
        side = role.row_link.get(obj.object_type)
        if side is None:
            return True
        if as_object is None:
            return False
        as_type, as_id = as_object.split(":", 1)
        neighbors = self.store.search_around(obj.object_type, obj.primary_key, side)
        return any(n.object_type == as_type and n.primary_key == as_id for n in neighbors)

    def redact(self, actor: str, obj: StoredObject) -> dict[str, Any]:
        _name, role, _as = self.role_for(actor)
        hidden = set(role.hide_properties.get(obj.object_type, []))
        return {k: v for k, v in obj.properties.items() if k not in hidden}

    def can_act(self, actor: str, action_type: str, targets: list[StoredObject]) -> None:
        _name, role, _as = self.role_for(actor)
        if "*" not in role.actions and action_type not in role.actions:
            raise SecurityError(f"{actor} cannot submit {action_type}")
        for obj in targets:
            if not self.can_read(actor, obj):
                raise SecurityError(f"{actor} cannot act on {obj.object_type}:{obj.primary_key}")

    def mcp_unattended_allowed(self, actor: str, action_type: str) -> bool:
        _name, role, _as = self.role_for(actor)
        return action_type in role.unattended_actions or "*" in role.unattended_actions
