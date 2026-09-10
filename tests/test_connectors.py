"""Data sources (connectors): data flows into the ontology through MCP-style sources."""

from __future__ import annotations

import shutil

import pytest

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel


@pytest.fixture
def kernel(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    return open_kernel(pack, tmp_path / "src.sqlite")


def test_register_and_pull_synthetic_source(kernel):
    body = kernel.register_source(
        "ship-feed",
        "synthetic",
        "Package",
        {"rows": [{"id": "SRC1", "status": "in_transit"}, {"id": "SRC2", "status": "delivered"}]},
        auto=False,
        description="a synthetic feed",
    )
    assert body["name"] == "ship-feed"
    assert body["object_type"] == "Package"
    listed = kernel.list_sources()["sources"]
    assert len(listed) == 1
    result = kernel.pull_source("ship-feed")
    assert result["count"] == 2
    obj = kernel.get_object("Package", "SRC1")
    assert obj["properties"]["status"] == "in_transit"
    runs = kernel.list_source_runs()["runs"]
    assert runs[0]["upserted"] == 2
    assert runs[0]["status"] == "ok"


def test_pull_unknown_source_raises(kernel):
    with pytest.raises(KeyError):
        kernel.pull_source("nope")


def test_register_source_unknown_object_type(kernel):
    with pytest.raises(ValueError):
        kernel.register_source("bad", "synthetic", "NotAType", {"rows": []})


def test_register_source_unknown_kind(kernel):
    with pytest.raises(ValueError):
        kernel.register_source("bad", "ftp", "Package", {"rows": []})


def test_pull_all_sources_only_runs_auto(kernel):
    kernel.register_source("manual", "synthetic", "Package", {"rows": [{"id": "M1", "status": "lost"}]})
    kernel.register_source("auto", "synthetic", "Package", {"rows": [{"id": "A1", "status": "in_transit"}]}, auto=True)
    result = kernel.pull_all_sources()
    names = [item["source"] for item in result["pulled"]]
    assert "auto" in names
    assert "manual" not in names
    assert kernel.store.get_object("Package", "A1") is not None
    assert kernel.store.get_object("Package", "M1") is None


def test_csv_source_reads_file(kernel, tmp_path):
    csv_path = tmp_path / "feed.csv"
    csv_path.write_text("id,status\nCSV1,lost\nCSV2,in_transit\n", encoding="utf-8")
    kernel.register_source("csv-feed", "csv", "Package", {"path": str(csv_path)})
    result = kernel.pull_source("csv-feed")
    assert result["count"] == 2
    assert kernel.get_object("Package", "CSV1")["properties"]["status"] == "lost"


def test_csv_source_missing_file_reports_error(kernel):
    kernel.register_source("bad-csv", "csv", "Package", {"path": "/no/such/file.csv"})
    with pytest.raises(ValueError):
        kernel.pull_source("bad-csv")
    runs = kernel.list_source_runs()["runs"]
    assert runs[0]["status"] == "error"


def test_callable_source(kernel):
    pulled = []

    def feed(store, record):
        obj = store.upsert_object("Package", {"id": "CALL1", "status": "lost"}, source="funnel")
        pulled.append(obj.id)
        from quinovo.connectors.base import SourceRun
        return SourceRun(upserted=[{"type": "Package", "id": "CALL1"}], detail="callable")

    kernel.register_source_callable("call-feed", "Package", feed, config={})
    result = kernel.pull_source("call-feed")
    assert result["count"] == 1
    assert "CALL1" in pulled


def test_delete_source(kernel):
    kernel.register_source("temp", "synthetic", "Package", {"rows": [{"id": "T1"}]})
    kernel.delete_source("temp")
    assert kernel.list_sources()["sources"] == []


def test_source_survives_reload(kernel):
    kernel.register_source("persist", "synthetic", "Package", {"rows": [{"id": "P1"}]})
    kernel.reload()
    listed = kernel.list_sources()["sources"]
    assert len(listed) == 1
    assert listed[0]["name"] == "persist"
