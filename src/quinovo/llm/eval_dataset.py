"""Langfuse dataset of Quinovo eval-template failures.

Live judges score observations tagged ``quinovo``. A failing score is upserted
into ``quinovo/eval-failures``. An experiment rule on that dataset reruns the
same judges automatically.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from quinovo.llm import tracing as lf
from quinovo.train.filters import _scrub
from quinovo.workspace import ROOT

DEFAULT_EVAL_DATASET = "quinovo/eval-failures"
TEMPLATE_PATH = ROOT / "evals" / "datasets" / "agent_run" / "template.json"
SKIP_ENVIRONMENTS = frozenset({"langfuse-llm-as-a-judge", "sdk-experiment"})

_DATASET_READY = False
_TEMPLATE: dict[str, Any] | None = None


def eval_dataset_name() -> str:
    return (
        os.environ.get("LANGFUSE_EVAL_DATASET", "").strip()
        or str(load_template().get("name") or DEFAULT_EVAL_DATASET)
    )


def load_template(path: Path | None = None) -> dict[str, Any]:
    global _TEMPLATE
    target = path or TEMPLATE_PATH
    if path is None and _TEMPLATE is not None:
        return _TEMPLATE
    payload = json.loads(target.read_text(encoding="utf-8"))
    if path is None:
        _TEMPLATE = payload
    return payload


def fail_values(trigger: dict[str, Any]) -> list[str]:
    when = trigger.get("fail_when") or {}
    if "equals" in when:
        return [_query_value(when["equals"])]
    found = when.get("in") or []
    return [_query_value(item) for item in found]


def score_failed(trigger: dict[str, Any], value: Any) -> bool:
    when = trigger.get("fail_when") or {}
    if "equals" in when:
        return _same_score(value, when["equals"])
    allowed = when.get("in")
    if isinstance(allowed, list):
        return any(_same_score(value, item) for item in allowed)
    return False


def passing_output(template: dict[str, Any] | None = None) -> dict[str, Any]:
    item = template or load_template()
    return dict(item.get("expected_output") or {})


def item_id_for(observation_id: str | None, trace_id: str | None) -> str:
    key = observation_id or trace_id or "unknown"
    return f"quinovo-eval-{key}"[:255]


def experiment_rule_body(
    dataset_id: str,
    evaluator_ids: list[str],
    *,
    name: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": True,
        "sampling": 1,
        "filter": [
            {
                "type": "boolean",
                "column": "isExperimentItemRootSpan",
                "operator": "=",
                "value": True,
            },
            {
                "type": "stringOptions",
                "column": "datasetId",
                "operator": "any of",
                "value": [dataset_id],
            },
        ],
        "evaluatorAssignments": [
            {"evaluatorId": evaluator_id} for evaluator_id in evaluator_ids
        ],
    }


def observation_item_input(observation: dict[str, Any]) -> dict[str, Any]:
    metadata = observation.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    tool_calls = (
        observation.get("toolCalls")
        or observation.get("tool_calls")
        or metadata.get("tool_calls")
        or metadata.get("toolCalls")
        or []
    )
    return {
        "user_input": _jsonish(observation.get("input")),
        "output": _jsonish(observation.get("output")),
        "tool_calls": _jsonish(tool_calls),
    }


def ensure_eval_dataset(client: Any | None = None) -> bool:
    """Create the Langfuse eval-failure dataset if it is missing. Never raises."""
    global _DATASET_READY
    if _DATASET_READY:
        return True
    if not lf.tracing_enabled():
        return False
    try:
        dataset = _get_or_create_dataset(client)
    except Exception:
        return False
    _DATASET_READY = bool(dataset)
    return _DATASET_READY


def collect_eval_failures(*, since_hours: float = 6, limit: int = 50) -> dict[str, Any]:
    """Upsert failing eval-template scores into the dataset. Never raises."""
    if not lf.tracing_enabled():
        return {"dataset": DEFAULT_EVAL_DATASET, "items": 0, "scores": 0}
    try:
        return _collect(since_hours=since_hours, limit=limit)
    except Exception:
        return {"dataset": eval_dataset_name(), "items": 0, "scores": 0}


def install_eval_dataset(*, collect: bool = False, dry_run: bool = False) -> int:
    """Create the dataset and the experiment rule that reruns catalog judges."""
    lf.load_langfuse_env()
    template = load_template()
    name = eval_dataset_name()
    if dry_run:
        print(json.dumps(_dataset_create_body(template, name), indent=2))
        print()
        print(
            json.dumps(
                experiment_rule_body(
                    "<dataset-id>", ["<evaluator-id>"], name=_rule_name(template)
                ),
                indent=2,
            )
        )
        return 0
    auth = _auth_header()
    if not auth:
        print("Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.", file=sys.stderr)
        return 1
    dataset = _get_or_create_dataset()
    if not dataset:
        print("could not create or load the eval dataset", file=sys.stderr)
        return 1
    dataset_id = str(dataset.get("id") or "")
    print(f"dataset {name} -> {dataset_id}")
    evaluator_ids = _latest_evaluator_ids(template)
    if not evaluator_ids:
        print(
            "no quinovo/* evaluators found; install judges first, then rerun",
            file=sys.stderr,
        )
    elif _rule_exists(_rule_name(template)):
        print(f"rule {_rule_name(template)} already exists")
    else:
        body = experiment_rule_body(
            dataset_id, list(evaluator_ids.values()), name=_rule_name(template)
        )
        status, response = request_json(
            method="POST",
            url=_url("/api/public/v2/evaluation-rules"),
            auth=auth,
            body=body,
        )
        if status not in (200, 201):
            print(
                f"dataset created, but experiment rule failed: HTTP {status}\n"
                f"{json.dumps(response, indent=2)}",
                file=sys.stderr,
            )
            return 1
        assigned = ", ".join(sorted(evaluator_ids))
        print(f"rule {response.get('id')} scores experiments with {assigned}")
    if collect:
        result = collect_eval_failures(since_hours=24, limit=100)
        print(f"collected {result['items']} items from {result['scores']} failing scores")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create the Quinovo eval-failure dataset and experiment rule."
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Also upsert recent failing judge scores into the dataset.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the dataset and rule bodies without calling Langfuse.",
    )
    args = parser.parse_args(argv)
    return install_eval_dataset(collect=args.collect, dry_run=args.dry_run)


def request_json(
    *,
    method: str,
    url: str,
    auth: str,
    body: dict[str, Any] | None = None,
    timeout: float = 20,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=context, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            payload: Any = json.loads(raw) if raw else {}
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            payload = {"message": raw or str(exc)}
        return exc.code, payload


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _same_score(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return _as_bool(left) is _as_bool(right) and _as_bool(left) is not None
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if left in (0, 1) and isinstance(right, bool):
            return bool(left) is right
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            return float(left) == float(right)
    return str(left).strip().lower() == str(right).strip().lower()


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, 1) and isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def _jsonish(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value
    return value if value is not None else ""


def _rule_name(template: dict[str, Any]) -> str:
    return str(template.get("rule_name") or template.get("name") or DEFAULT_EVAL_DATASET)


def _dataset_create_body(template: dict[str, Any], name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": template.get("description") or "",
        "metadata": template.get("metadata")
        or {"author": "quinovo", "type": "eval-failures"},
        "inputSchema": template.get("input_schema"),
        "expectedOutputSchema": template.get("expected_output_schema"),
    }


def _base_url() -> str:
    lf.load_langfuse_env()
    return (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "http://localhost:3000"
    ).rstrip("/")


def _url(path: str, query: dict[str, Any] | None = None) -> str:
    url = f"{_base_url()}{path}"
    if not query:
        return url
    parts = urllib.parse.urlencode(
        {key: value for key, value in query.items() if value is not None},
        doseq=True,
    )
    return f"{url}?{parts}"


def _auth_header() -> str:
    lf.load_langfuse_env()
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not public or not secret:
        return ""
    token = base64.b64encode(f"{public}:{secret}".encode()).decode("ascii")
    return f"Basic {token}"


def _sdk_create_kwargs(template: dict[str, Any], name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": template.get("description") or "",
        "metadata": template.get("metadata")
        or {"author": "quinovo", "type": "eval-failures"},
        "input_schema": template.get("input_schema"),
        "expected_output_schema": template.get("expected_output_schema"),
    }


def _get_or_create_dataset(client: Any | None = None) -> dict[str, Any] | None:
    template = load_template()
    name = eval_dataset_name()
    item = client if client is not None else None
    if item is not None:
        try:
            found = item.get_dataset(name, fetch_items_page_size=1)
            return found if isinstance(found, dict) else {"name": name}
        except Exception:
            created = item.create_dataset(**_sdk_create_kwargs(template, name))
            return created if isinstance(created, dict) else {"name": name}
    auth = _auth_header()
    if not auth:
        return None
    encoded = urllib.parse.quote(name, safe="")
    status, payload = request_json(
        method="GET",
        url=_url(f"/api/public/v2/datasets/{encoded}"),
        auth=auth,
    )
    if status == 200 and isinstance(payload, dict) and payload.get("id"):
        return payload
    status, payload = request_json(
        method="POST",
        url=_url("/api/public/v2/datasets"),
        auth=auth,
        body=_dataset_create_body(template, name),
    )
    if status in (200, 201) and isinstance(payload, dict):
        return payload
    if status in (400, 409):
        status, payload = request_json(
            method="GET",
            url=_url(f"/api/public/v2/datasets/{encoded}"),
            auth=auth,
        )
        if status == 200 and isinstance(payload, dict):
            return payload
    return None


def _list_pages(path: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    auth = _auth_header()
    if not auth:
        return []
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    params = dict(query or {})
    params.setdefault("limit", 100)
    while True:
        if cursor:
            params["cursor"] = cursor
        status, payload = request_json(
            method="GET",
            url=_url(path, params),
            auth=auth,
        )
        if status != 200 or not isinstance(payload, dict):
            break
        chunk = payload.get("data")
        if isinstance(chunk, list):
            rows.extend(item for item in chunk if isinstance(item, dict))
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        cursor = str(meta.get("cursor") or "") or None
        if not cursor or not chunk:
            break
    return rows


def _latest_evaluator_ids(template: dict[str, Any]) -> dict[str, str]:
    prefix = str(template.get("evaluator_name_prefix") or "quinovo/")
    wanted = {
        f"{prefix}{trigger['template']}"
        for trigger in template.get("triggers") or []
        if trigger.get("template")
    }
    found: dict[str, str] = {}
    for evaluator in _list_pages("/api/public/v2/evaluators"):
        name = str(evaluator.get("name") or "")
        evaluator_id = str(evaluator.get("id") or "")
        if name in wanted and name not in found and evaluator_id:
            found[name] = evaluator_id
        if len(found) == len(wanted):
            break
    return found


def _rule_exists(name: str) -> bool:
    for rule in _list_pages("/api/public/v2/evaluation-rules"):
        if str(rule.get("name") or "") == name:
            return True
    return False


def _collect(*, since_hours: float, limit: int) -> dict[str, Any]:
    template = load_template()
    if not ensure_eval_dataset():
        return {"dataset": eval_dataset_name(), "items": 0, "scores": 0}
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    score_count = 0
    for trigger in template.get("triggers") or []:
        for score in _failing_scores(trigger, since=since, limit=limit):
            subject = score.get("subject") if isinstance(score.get("subject"), dict) else {}
            if str(subject.get("kind") or "") == "experiment":
                continue
            environment = str(score.get("environment") or "")
            if environment in SKIP_ENVIRONMENTS:
                continue
            observation_id = (
                str(subject.get("id") or "") if subject.get("kind") == "observation" else ""
            )
            trace_id = str(subject.get("traceId") or subject.get("id") or "")
            if not observation_id and not trace_id:
                continue
            grouped[(trace_id, observation_id)].append({"trigger": trigger, "score": score})
            score_count += 1
    written = 0
    for (trace_id, observation_id), hits in grouped.items():
        observation = _load_observation(trace_id, observation_id)
        if observation is None:
            continue
        if _skip_observation(observation):
            continue
        if _upsert_item(template, observation, hits, trace_id, observation_id):
            written += 1
    lf.flush_langfuse()
    return {"dataset": eval_dataset_name(), "items": written, "scores": score_count}


def _failing_scores(
    trigger: dict[str, Any],
    *,
    since: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    values = fail_values(trigger)
    if not values:
        return []
    query = {
        "name": str(trigger.get("score") or trigger.get("template") or ""),
        "dataType": str(trigger.get("data_type") or "BOOLEAN"),
        "value": ",".join(values),
        "source": "EVAL",
        "fields": "subject,details",
        "fromTimestamp": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": min(limit, 100),
    }
    return _list_pages("/api/public/v3/scores", query)


def _skip_observation(observation: dict[str, Any]) -> bool:
    environment = str(observation.get("environment") or "")
    if environment in SKIP_ENVIRONMENTS:
        return True
    tags = observation.get("tags") or []
    if isinstance(tags, list) and any(str(tag) == "experiment" for tag in tags):
        return True
    return False


def _load_observation(trace_id: str, observation_id: str) -> dict[str, Any] | None:
    auth = _auth_header()
    if not auth:
        return None
    query: dict[str, Any] = {
        "fields": "core,basic,io,metadata,trace_context",
        "limit": 50,
    }
    if trace_id:
        query["traceId"] = trace_id
    status, payload = request_json(
        method="GET",
        url=_url("/api/public/v2/observations", query),
        auth=auth,
    )
    rows = payload.get("data") if status == 200 and isinstance(payload, dict) else None
    if isinstance(rows, list) and rows:
        if observation_id:
            for row in rows:
                if isinstance(row, dict) and str(row.get("id") or "") == observation_id:
                    return row
        for row in rows:
            if isinstance(row, dict) and row.get("isRootObservation"):
                return row
        first = rows[0]
        return first if isinstance(first, dict) else None
    if observation_id:
        status, payload = request_json(
            method="GET",
            url=_url(
                f"/api/public/observations/{urllib.parse.quote(observation_id, safe='')}"
            ),
            auth=auth,
        )
        if status == 200 and isinstance(payload, dict):
            return payload
    return None


def _upsert_item(
    template: dict[str, Any],
    observation: dict[str, Any],
    hits: list[dict[str, Any]],
    trace_id: str,
    observation_id: str,
) -> bool:
    source_observation = observation_id or str(observation.get("id") or "")
    source_trace = trace_id or str(observation.get("traceId") or "")
    failed = sorted(
        {
            str(hit["trigger"].get("template") or hit["trigger"].get("score") or "")
            for hit in hits
            if hit.get("trigger")
        }
    )
    scores = {
        str(hit["trigger"].get("score") or hit["trigger"].get("template") or ""): (
            hit["score"].get("value")
        )
        for hit in hits
        if hit.get("trigger") and isinstance(hit.get("score"), dict)
    }
    body = {
        "datasetName": eval_dataset_name(),
        "id": item_id_for(source_observation, source_trace),
        "input": _scrub(observation_item_input(observation)),
        "expectedOutput": passing_output(template),
        "metadata": {
            "failed": failed,
            "scores": scores,
            "source": "eval-templates",
            "environment": lf.tracing_environment(),
        },
        "sourceTraceId": source_trace or None,
        "sourceObservationId": source_observation or None,
    }
    auth = _auth_header()
    if not auth:
        return False
    status, _payload = request_json(
        method="POST",
        url=_url("/api/public/dataset-items"),
        auth=auth,
        body=body,
    )
    return status in (200, 201)


if __name__ == "__main__":
    raise SystemExit(main())
