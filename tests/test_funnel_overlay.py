from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import EXAMPLE_PACK
from quinovo.kernel import open_kernel


def test_seed_reload_does_not_un_deliver(tmp_path):
    kernel = open_kernel(EXAMPLE_PACK, tmp_path / "overlay.sqlite")
    kernel.apply_action(
        "mark_delivered",
        {"package": {"type": "Package", "id": "1Z999"}},
        "warehouse",
        channel="human",
    )
    assert kernel.get_object("Package", "1Z999")["properties"]["status"] == "delivered"
    kernel.reload_seed()
    box = kernel.get_object("Package", "1Z999")
    assert box["properties"]["status"] == "delivered"


def test_human_notify_buyer_without_inference(client: TestClient):
    applied = client.post(
        "/actions/notify_buyer",
        json={"parameters": {"package": {"type": "Package", "id": "1Z999"}}, "actor": "warehouse"},
    )
    assert applied.status_code == 200
    assert applied.json()["objects"][0]["properties"]["buyer_notified"] == "true"
