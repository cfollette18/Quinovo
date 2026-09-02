from __future__ import annotations

import pytest

from quinovo.kernel import open_kernel


def test_property_and_join_rules_and_provenance(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "c.sqlite")
    facts = kernel.run_inference()["facts"]
    by_pred = {item["predicate"]: item for item in facts}
    assert by_pred["open"]["value"] == "true"
    assert by_pred["story"]["value"] == "complete"
    explained = kernel.explain_fact(by_pred["story"]["id"])
    assert "buyer" in str(explained["why"])


def test_series_and_timesfm_plugin(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "c.sqlite")
    kernel.append_series("Package", "1Z999", "late_risk", "2026-09-01T00:00:00Z", 0.2)
    kernel.append_series("Package", "1Z999", "late_risk", "2026-09-02T00:00:00Z", 0.4)
    series = kernel.get_series("Package", "1Z999", "late_risk")
    assert len(series["points"]) == 2
    written = kernel.forecast_from_series("Package", "1Z999", "late_risk", 24, "timesfm-2.5", 0.86)
    assert written["forecast"]["model"] == "timesfm-2.5"
    assert written["forecast"]["point"] == 0.4
    assert written["forecast"]["actionable"] is True


def test_timesfm_30_is_off_the_default_path(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "c.sqlite")
    kernel.append_series("Package", "1Z999", "late_risk", "2026-09-01T00:00:00Z", 0.2)
    with pytest.raises(ValueError, match="3.0"):
        kernel.forecast_from_series("Package", "1Z999", "late_risk", 24, "timesfm-3.0")


def test_pack_function_bobs_open_orders(tmp_path):
    kernel = open_kernel(db_path=tmp_path / "c.sqlite")
    result = kernel.run_pack_function("bobs_open_orders", {"person_id": "bob"})
    assert "1Z999" in result
