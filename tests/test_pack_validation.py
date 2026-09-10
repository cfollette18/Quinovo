"""Every shipped pack and test fixture passes full pack validation.

Schema checks alone do not catch a rule that names a missing type or a
security role that grants a missing action — validate_pack does. A broken
pack fails here in CI, not in front of a user at runtime.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import CLINIC_PACK, EXAMPLE_PACK
from quinovo.kernel import open_kernel
from quinovo.pack.validate import PackValidationError, validate_pack
from quinovo.workspace import ROOT

PACK_DIRS = sorted(
    path.parent
    for root in (ROOT / "packs", ROOT / "tests" / "fixtures")
    for path in root.glob("*/ontology.yaml")
)


@pytest.mark.parametrize("pack_dir", PACK_DIRS, ids=[p.name for p in PACK_DIRS])
def test_pack_passes_full_validation(pack_dir: Path) -> None:
    validate_pack(pack_dir)


def test_every_pack_boots_a_kernel(tmp_path: Path) -> None:
    for index, pack_dir in enumerate((EXAMPLE_PACK, CLINIC_PACK)):
        kernel = open_kernel(pack_dir, tmp_path / f"pack-{index}.sqlite")
        kernel.store.close()


def _broken_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "broken"
    shutil.copytree(EXAMPLE_PACK, dest)
    return dest


def _edit_yaml(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_bad_rule_reference_fails_loudly(tmp_path: Path) -> None:
    pack = _broken_copy(tmp_path)

    def break_rule(doc: dict[str, Any]) -> None:
        doc["rules"][0]["source_type"] = "Ghost"

    _edit_yaml(pack / "inference.yaml", break_rule)
    with pytest.raises(PackValidationError, match=r"inference\.yaml.*Ghost"):
        validate_pack(pack)
    with pytest.raises(PackValidationError, match=r"inference\.yaml"):
        open_kernel(pack, tmp_path / "db.sqlite")


def test_bad_security_reference_fails_loudly(tmp_path: Path) -> None:
    pack = _broken_copy(tmp_path)

    def break_role(doc: dict[str, Any]) -> None:
        doc["roles"]["warehouse"]["actions"] = ["vanish"]

    _edit_yaml(pack / "security.yaml", break_role)
    with pytest.raises(PackValidationError, match=r"security\.yaml.*vanish"):
        validate_pack(pack)


def test_bad_seed_link_fails_loudly(tmp_path: Path) -> None:
    pack = _broken_copy(tmp_path)

    def break_link(doc: dict[str, Any]) -> None:
        doc["links"]["contains"][0]["to_id"] = "missing-product"

    _edit_yaml(pack / "seed.yaml", break_link)
    with pytest.raises(PackValidationError, match=r"seed\.yaml.*missing-product"):
        validate_pack(pack)


def test_seed_rejects_legacy_from_to_keys(tmp_path: Path) -> None:
    pack = _broken_copy(tmp_path)

    def break_keys(doc: dict[str, Any]) -> None:
        doc["links"]["contains"][0] = {"from": "1Z999", "to": "lipstick-1"}

    _edit_yaml(pack / "seed.yaml", break_keys)
    with pytest.raises(Exception, match=r"from_id"):
        validate_pack(pack)
