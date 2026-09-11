from __future__ import annotations

from fastapi.testclient import TestClient


def test_rail_includes_train_and_settings(client: TestClient):
    page = client.get("/chat")
    assert page.status_code == 200
    assert 'href="/train"' in page.text
    assert 'href="/settings"' in page.text
    assert 'title="Train"' in page.text
    assert 'title="Settings"' in page.text


def test_train_page_is_human_and_has_json_expander(client: TestClient):
    page = client.get("/train")
    assert page.status_code == 200
    text = page.text
    assert "Choose what this specialist should learn" in text
    assert "Only confirmed items" in text
    assert "Include things still waiting for a look" in text
    assert "Small specialist" in text
    assert "Things" in text
    assert "Connections" in text
    assert "What Quinovo noticed" in text
    assert "What changed" in text
    assert "json-panel" not in text
    assert "<pre" not in text
    assert "page-head" in text
    assert "crumbs" in text
    assert "<h1>Train</h1>" in text
    assert "turn down a proposal" in text
    assert "LoRA" not in text
    assert "fine-tune" not in text
    assert "super-secret" not in text
    assert "MINIMAX_API_KEY" not in text
    assert '"object_types"' not in text


def test_train_filter_returns_live_records(client: TestClient):
    preview = client.get("/train/data").json()
    assert preview["counts"]["total"] >= 1
    assert preview["records"]
    families = {row["family"] for row in preview["records"]}
    assert "things" in families
    titles = " ".join(row["title"] for row in preview["records"])
    assert "1Z999" in titles or "Bob" in titles or "Cherry" in titles
    things = client.get("/train/data", params={"kinds": "things", "types": "Package"}).json()
    assert things["records"]
    assert all(row["family"] == "things" for row in things["records"])
    assert all(row["type"] == "Package" for row in things["records"])


def test_train_dataset_and_job_persist(client: TestClient):
    created = client.post(
        "/train/datasets",
        json={
            "name": "Confirmed things",
            "filters": {"kinds": "things", "status": "confirmed"},
        },
    )
    assert created.status_code == 200
    dataset = created.json()
    assert dataset["name"] == "Confirmed things"
    assert dataset["record_count"] >= 1
    assert "records" not in dataset
    listed = client.get("/train/datasets").json()
    assert any(row["id"] == dataset["id"] for row in listed["datasets"])

    job_res = client.post(
        "/train/jobs",
        json={
            "name": "Thing specialist",
            "dataset_id": dataset["id"],
            "size_class": "small",
        },
    )
    assert job_res.status_code == 200
    job = job_res.json()
    assert job["size_label"] == "Small specialist"
    assert job["status"] == "prepared"
    assert job["example_count"] >= 1
    assert job["jsonl_path"].endswith(".jsonl")
    jobs = client.get("/train/jobs").json()
    assert any(row["id"] == job["id"] for row in jobs["jobs"])

    kernel = client.app.state.kernel
    jsonl = kernel.train_root() / job["jsonl_path"]
    assert jsonl.is_file()
    line = jsonl.read_text(encoding="utf-8").splitlines()[0]
    assert "instruction" in line
    assert "input" in line
    assert "output" in line
    assert "packs/" not in str(jsonl)
    assert kernel.train_root() == kernel.store.db_path.parent / "train"


def test_train_strips_secret_fields_and_honors_exclude(client: TestClient):
    from quinovo.train import _scrub

    cleaned = _scrub({"name": "Hidden", "api_key": "super-secret-key-do-not-leak"})
    assert cleaned["name"] == "Hidden"
    assert "api_key" not in cleaned
    preview = client.get(
        "/train/data",
        params={"kinds": "things", "types": "Package", "exclude_fields": "route_code"},
    ).json()
    assert preview["records"]
    for row in preview["records"]:
        assert "route_code" not in (row.get("fields") or {})
    page = client.get("/train")
    assert "super-secret-key-do-not-leak" not in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
