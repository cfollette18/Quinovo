"""Cross-file pack validation: every reference resolves, or the pack does not load.

Each pack file parses on its own; this module checks what one file says about
another — rule source_types against the ontology, role actions against the
action types, seed link endpoints against the seeded objects. A broken pack
fails at load with the file and the bad reference named.
"""

from __future__ import annotations

from pathlib import Path

from quinovo.inference.load import load_ruleset
from quinovo.inference.rules import InferenceRuleset
from quinovo.language.load import load_ontology
from quinovo.language.models import Ontology
from quinovo.pack.seed import SeedDoc, load_seed_doc
from quinovo.security import SecurityPolicy, load_security


class PackValidationError(ValueError):
    """A pack file references something the pack does not declare."""


def link_sides(ontology: Ontology, object_type: str) -> set[str]:
    """Legal link side names for a type: from_names out, to_names in."""
    sides: set[str] = set()
    for link in ontology.link_types:
        if link.from_type == object_type:
            sides.add(link.from_name)
        if link.to_type == object_type:
            sides.add(link.to_name)
    return sides


def _object_names(ontology: Ontology) -> set[str]:
    return {item.api_name for item in ontology.object_types}


def _action_names(ontology: Ontology) -> set[str]:
    return {item.api_name for item in ontology.action_types}


def validate_ruleset(
    ruleset: InferenceRuleset,
    ontology: Ontology,
    source: str = "inference.yaml",
) -> None:
    names = [rule.api_name for rule in ruleset.rules]
    if len(names) != len(set(names)):
        raise PackValidationError(f"{source}: duplicate rule api_name")
    object_names = _object_names(ontology)
    for rule in ruleset.rules:
        if rule.source_type not in object_names:
            raise PackValidationError(
                f"{source}: rule {rule.api_name}: source_type "
                f"{rule.source_type!r} is not an object type"
            )
        source_def = ontology.object_type(rule.source_type)
        properties = {prop.api_name for prop in source_def.properties}
        if rule.when_property is not None and rule.when_property.api_name not in properties:
            raise PackValidationError(
                f"{source}: rule {rule.api_name}: when_property "
                f"{rule.when_property.api_name!r} is not a property of {rule.source_type}"
            )
        if rule.when_age is not None and rule.when_age.property not in properties:
            raise PackValidationError(
                f"{source}: rule {rule.api_name}: when_age "
                f"{rule.when_age.property!r} is not a property of {rule.source_type}"
            )
        sides = link_sides(ontology, rule.source_type)
        watched = ([rule.when_link] if rule.when_link is not None else []) + list(
            rule.when_links
        )
        for side in watched:
            if side not in sides:
                raise PackValidationError(
                    f"{source}: rule {rule.api_name}: link side {side!r} is not "
                    f"a link side of {rule.source_type} (known: {sorted(sides)})"
                )
        if rule.then_link is not None:
            then = rule.then_link
            link_names = {link.api_name for link in ontology.link_types}
            if then.link_type not in link_names:
                raise PackValidationError(
                    f"{source}: rule {rule.api_name}: then_link link_type "
                    f"{then.link_type!r} is not a link type"
                )
            if then.to_type not in object_names:
                raise PackValidationError(
                    f"{source}: rule {rule.api_name}: then_link to_type "
                    f"{then.to_type!r} is not an object type"
                )
            link_def = ontology.link_type(then.link_type)
            if link_def.from_type != rule.source_type or link_def.to_type != then.to_type:
                raise PackValidationError(
                    f"{source}: rule {rule.api_name}: then_link {then.link_type} "
                    f"is {link_def.from_type}->{link_def.to_type}, "
                    f"not {rule.source_type}->{then.to_type}"
                )


def validate_security(
    policy: SecurityPolicy,
    ontology: Ontology,
    source: str = "security.yaml",
) -> None:
    object_names = _object_names(ontology)
    action_names = _action_names(ontology)
    for role_name, role in policy.roles.items():
        for action in [*role.actions, *role.unattended_actions]:
            if action != "*" and action not in action_names:
                raise PackValidationError(
                    f"{source}: role {role_name}: action {action!r} is not an action type"
                )
        for type_name in role.types:
            if type_name != "*" and type_name not in object_names:
                raise PackValidationError(
                    f"{source}: role {role_name}: type {type_name!r} is not an object type"
                )
        for type_name, side in role.row_link.items():
            if type_name not in object_names:
                raise PackValidationError(
                    f"{source}: role {role_name}: row_link key {type_name!r} "
                    f"is not an object type"
                )
            sides = link_sides(ontology, type_name)
            if side not in sides:
                raise PackValidationError(
                    f"{source}: role {role_name}: row_link side {side!r} is not "
                    f"a link side of {type_name} (known: {sorted(sides)})"
                )
        for type_name, props in role.hide_properties.items():
            if type_name not in object_names:
                raise PackValidationError(
                    f"{source}: role {role_name}: hide_properties key {type_name!r} "
                    f"is not an object type"
                )
            known = {prop.api_name for prop in ontology.object_type(type_name).properties}
            for prop in props:
                if prop not in known:
                    raise PackValidationError(
                        f"{source}: role {role_name}: hide_properties {prop!r} "
                        f"is not a property of {type_name}"
                    )
    for user, binding in policy.bindings.items():
        if binding.role not in policy.roles:
            raise PackValidationError(
                f"{source}: binding {user}: role {binding.role!r} is not a declared role"
            )
        if binding.as_object is not None:
            as_type, _, _ = binding.as_object.partition(":")
            if as_type not in object_names:
                raise PackValidationError(
                    f"{source}: binding {user}: as_object {binding.as_object!r} "
                    f"must be 'Type:id' with a declared object type"
                )


def validate_seed(
    seed: SeedDoc,
    ontology: Ontology,
    source: str = "seed.yaml",
) -> None:
    object_names = _object_names(ontology)
    seeded: dict[str, set[str]] = {}
    for type_name, rows in seed.objects.items():
        if type_name not in object_names:
            raise PackValidationError(
                f"{source}: objects: {type_name!r} is not an object type"
            )
        type_def = ontology.object_type(type_name)
        properties = {prop.api_name for prop in type_def.properties}
        ids = seeded.setdefault(type_name, set())
        for row in rows:
            object_id = row.get(type_def.primary_key)
            if object_id is None:
                raise PackValidationError(
                    f"{source}: {type_name} row is missing primary key "
                    f"{type_def.primary_key!r}"
                )
            for key in row:
                if key not in properties:
                    raise PackValidationError(
                        f"{source}: object {type_name}:{object_id}: "
                        f"unknown property {key!r}"
                    )
            missing = [
                prop.api_name
                for prop in type_def.properties
                if prop.required and prop.api_name not in row
            ]
            if missing:
                raise PackValidationError(
                    f"{source}: object {type_name}:{object_id}: "
                    f"missing required properties {missing}"
                )
            ids.add(str(object_id))
    for link_name, rows in seed.links.items():
        link_names = {link.api_name for link in ontology.link_types}
        if link_name not in link_names:
            raise PackValidationError(
                f"{source}: links: {link_name!r} is not a link type"
            )
        link_def = ontology.link_type(link_name)
        for row in rows:
            if row.from_id not in seeded.get(link_def.from_type, set()):
                raise PackValidationError(
                    f"{source}: link {link_name}: from_id {row.from_id!r} "
                    f"is not a seeded {link_def.from_type}"
                )
            if row.to_id not in seeded.get(link_def.to_type, set()):
                raise PackValidationError(
                    f"{source}: link {link_name}: to_id {row.to_id!r} "
                    f"is not a seeded {link_def.to_type}"
                )


def validate_pack(pack_dir: str | Path) -> None:
    """Load every pack document and check every cross-file reference."""
    pack_dir = Path(pack_dir)
    ontology = load_ontology(pack_dir / "ontology.yaml")
    rules_path = pack_dir / "inference.yaml"
    if rules_path.exists():
        validate_ruleset(load_ruleset(rules_path), ontology, source=str(rules_path))
    security_path = pack_dir / "security.yaml"
    if security_path.exists():
        validate_security(load_security(security_path), ontology, source=str(security_path))
    seed_path = pack_dir / "seed.yaml"
    if seed_path.exists():
        validate_seed(load_seed_doc(seed_path), ontology, source=str(seed_path))
