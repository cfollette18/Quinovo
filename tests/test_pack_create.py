"""quinovo.pack.create — scaffold a new pack from a spec dict or YAML.

The spec's `ontology` key is the full ontology document shape that
`load_ontology` validates: a top-level mapping with `ontology: {meta}` and
sibling keys `object_types`, `link_types`, `action_types`, etc. — exactly
the shape of `packs/example/ontology.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from quinovo.pack.create import PackCreateError, create_pack


def _widget_type() -> dict:
    return {
        "api_name": "Widget",
        "primary_key": "id",
        "title_property": "name",
        "description": "a widget",
        "properties": [
            {"api_name": "id", "type": "string"},
            {"api_name": "name", "type": "string"},
        ],
    }


def _meta(api: str, **extra: object) -> dict:
    meta = {"api_name": api, "display_name": api.title(), "description": api}
    meta.update(extra)
    return meta


def test_create_pack_writes_minimum_files(tmp_path: Path) -> None:
    spec = {
        "ontology": {
            "ontology": _meta("tmpspec"),
            "object_types": [_widget_type()],
        },
        "seed": {
            "objects": {"Widget": [{"id": "w1", "name": "first"}]},
            "links": {},
        },
    }
    out = create_pack(tmp_path / "myworld", spec)
    assert (out / "ontology.yaml").exists()
    assert (out / "seed.yaml").exists()
    assert out.name == "myworld"


def test_create_pack_rejects_missing_ontology(tmp_path: Path) -> None:
    with pytest.raises(PackCreateError):
        create_pack(tmp_path / "bad", {"seed": {"objects": {}, "links": {}}})


def test_create_pack_rejects_invalid_ontology_via_loader(tmp_path: Path) -> None:
    # property.type is constrained to PropertyType; passing a bogus type
    # should trip Pydantic's enum check.
    bad = {
        "ontology": {
            "ontology": _meta("x"),
            "object_types": [
                {
                    "api_name": "BadWidget",
                    "primary_key": "id",
                    "title_property": "id",
                    "description": "bad",
                    "properties": [{"api_name": "id", "type": "not_a_real_type"}],
                }
            ],
        }
    }
    with pytest.raises(Exception):
        create_pack(tmp_path / "bad", bad)


def test_create_pack_refuses_non_empty_dest(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "junk").write_text("nope")
    with pytest.raises(PackCreateError):
        create_pack(occupied, {"ontology": {"ontology": _meta("x")}})


def test_create_pack_optional_inference_file(tmp_path: Path) -> None:
    spec = {
        "ontology": {
            "ontology": _meta("withrules"),
            "object_types": [
                {
                    "api_name": "Thing",
                    "primary_key": "id",
                    "title_property": "id",
                    "description": "t",
                    "properties": [{"api_name": "id", "type": "string"}],
                }
            ],
        },
        "inference": {
            "rules": [
                {
                    "api_name": "thing_open",
                    "kind": "property_fact",
                    "description": "t",
                    "source_type": "Thing",
                    "confidence": 0.9,
                    "when_property": {"api_name": "id", "equals": "anything"},
                    "then_fact": {"predicate": "open", "value": "true"},
                }
            ]
        },
    }
    out = create_pack(tmp_path / "withrules", spec)
    assert (out / "inference.yaml").exists()
