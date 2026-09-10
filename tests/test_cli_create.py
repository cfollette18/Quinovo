"""quinovo create — CLI subcommand tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "quinovo.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        check=False,
    )


def test_cli_create_from_spec(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        """
ontology:
  ontology:
    api_name: cliworld
    display_name: CLI World
    description: from cli
  object_types:
    - api_name: Item
      primary_key: id
      title_property: name
      description: i
      properties:
        - api_name: id
          type: string
        - api_name: name
          type: string
seed:
  objects:
    Item:
      - id: i1
        name: alpha
  links: {}
""",
        encoding="utf-8",
    )
    dest = tmp_path / "myworld"
    result = _run_cli("create", str(dest), "--from-spec", str(spec_path))
    assert result.returncode == 0, result.stderr
    assert (dest / "ontology.yaml").exists()
    assert (dest / "seed.yaml").exists()


def test_cli_create_with_missing_ontology(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text("seed: {}\n", encoding="utf-8")
    dest = tmp_path / "bad"
    result = _run_cli("create", str(dest), "--from-spec", str(spec_path))
    assert result.returncode != 0
    assert "ontology" in result.stderr.lower() or "missing" in result.stderr.lower()
