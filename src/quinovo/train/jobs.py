"""Specialist training jobs over saved datasets."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from quinovo.apps.humanize import size_class_label
from quinovo.train.datasets import (
    _new_id,
    _now,
    _read_list,
    _write_list,
    get_dataset,
    write_jsonl,
)
from quinovo.train.filters import TrainError, parse_size_class


def list_jobs(root: Path) -> list[dict[str, Any]]:
    return _read_list(root / "jobs.json", "jobs")


def _optional_trainer(job: dict[str, Any], root: Path) -> dict[str, Any]:
    command = (os.environ.get("QUINOVO_TRAIN_CMD") or "").strip()
    if not command:
        job["status"] = "prepared"
        job["note"] = (
            "The training file is ready. A GPU trainer is not installed — "
            "this job records the set and the small-specialist size."
        )
        return job
    jsonl = root / str(job["jsonl_path"])
    spec = root / "jobs" / f"{job['id']}.json"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(json.dumps(job, indent=2, default=str) + "\n", encoding="utf-8")
    job["status"] = "running"
    try:
        completed = subprocess.run(
            [*command.split(), "--jsonl", str(jsonl), "--job", str(spec), "--size", job["size_class"]],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        job["status"] = "failed"
        job["note"] = f"Could not start the optional trainer: {exc}"
        return job
    if completed.returncode == 0:
        job["status"] = "ready"
        job["note"] = "The optional trainer finished."
    else:
        job["status"] = "failed"
        err = (completed.stderr or completed.stdout or "trainer exited").strip()
        job["note"] = err[:240]
    return job


def create_job(
    root: Path,
    *,
    name: str,
    dataset_id: str,
    size_class: str = "small",
) -> dict[str, Any]:
    label = name.strip()
    if not label:
        raise TrainError("Give this specialist a name.")
    size = parse_size_class(size_class)
    dataset = get_dataset(root, dataset_id)
    if dataset is None:
        raise TrainError("That saved set was not found.")
    records = list(dataset.get("records") or [])
    job_id = _new_id("job")
    export_rel = f"exports/{job_id}.jsonl"
    write_jsonl(root / export_rel, records)
    job: dict[str, Any] = {
        "id": job_id,
        "name": label,
        "dataset_id": dataset_id,
        "dataset_name": dataset.get("name"),
        "size_class": size,
        "size_label": size_class_label(size),
        "status": "prepared",
        "created_at": _now(),
        "jsonl_path": export_rel,
        "example_count": len(records),
        "note": "",
    }
    job = _optional_trainer(job, root)
    rows = list_jobs(root)
    rows.append(job)
    _write_list(root / "jobs.json", "jobs", rows)
    return job


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "dataset_id": job.get("dataset_id"),
        "dataset_name": job.get("dataset_name"),
        "size_class": job.get("size_class"),
        "size_label": job.get("size_label"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "jsonl_path": job.get("jsonl_path"),
        "example_count": job.get("example_count"),
        "note": job.get("note"),
    }
