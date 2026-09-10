"""Train filters: parse and validate the filter DSL for specialist sets."""

from __future__ import annotations

from typing import Any, Literal

from quinovo.apps.humanize import family_label, title_case

TrainFamily = Literal["things", "connections", "noticed", "changed"]
ReviewGate = Literal["all", "confirmed", "needs_look"]
SizeClass = Literal["tiny", "small", "medium"]
JobStatus = Literal["prepared", "running", "ready", "failed"]

FAMILIES: tuple[TrainFamily, ...] = ("things", "connections", "noticed", "changed")
REVIEW_GATES: tuple[ReviewGate, ...] = ("all", "confirmed", "needs_look")
SIZE_CLASSES: tuple[SizeClass, ...] = ("tiny", "small", "medium")

COLLECT_CAP = 5000
PREVIEW_DEFAULT = 80
SNAPSHOT_CAP = 2000

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "authorization",
    "private_key",
    "access_token",
    "refresh_token",
}


class TrainError(ValueError):
    """User-facing training or filter error."""


def _is_secret_key(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    if lowered in _SECRET_KEYS:
        return True
    return lowered.endswith(("_key", "_token", "_secret", "_password"))


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if not _is_secret_key(str(key))
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_family(value: str) -> TrainFamily:
    match value:
        case "things" | "connections" | "noticed" | "changed":
            return value
        case _ as other:
            raise TrainError(f"unknown kind of data: {other}")


def parse_review_gate(value: str) -> ReviewGate:
    match value:
        case "all" | "confirmed" | "needs_look":
            return value
        case "pending":
            return "needs_look"
        case _ as other:
            raise TrainError(f"unknown review filter: {other}")


def parse_size_class(value: str) -> SizeClass:
    match value:
        case "tiny" | "small" | "medium":
            return value
        case _ as other:
            raise TrainError(f"unknown specialist size: {other}")


def parse_filters(
    *,
    kinds: str | list[str] | None = None,
    types: str | list[str] | None = None,
    status: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_fields: str | list[str] | None = None,
    exclude_fields: str | list[str] | None = None,
    only_approved: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    kind_list: list[str]
    if isinstance(kinds, list):
        kind_list = [str(item) for item in kinds if item]
    else:
        kind_list = _csv(kinds)
    families = [parse_family(item) for item in kind_list] if kind_list else list(FAMILIES)

    type_list: list[str]
    if isinstance(types, list):
        type_list = [str(item) for item in types if item]
    else:
        type_list = _csv(types)

    include_list: list[str]
    if isinstance(include_fields, list):
        include_list = [str(item) for item in include_fields if item]
    else:
        include_list = _csv(include_fields)

    exclude_list: list[str]
    if isinstance(exclude_fields, list):
        exclude_list = [str(item) for item in exclude_fields if item]
    else:
        exclude_list = _csv(exclude_fields)

    gate = parse_review_gate(status or "all")
    shown = PREVIEW_DEFAULT if limit is None else max(1, min(int(limit), COLLECT_CAP))
    until_text = (until or "").strip()
    if len(until_text) == 10 and until_text[4:5] == "-" and until_text[7:8] == "-":
        until_text = until_text + "T23:59:59"
    return {
        "kinds": families,
        "types": type_list,
        "status": gate,
        "q": (q or "").strip(),
        "since": (since or "").strip(),
        "until": until_text,
        "include_fields": include_list,
        "exclude_fields": exclude_list,
        "only_approved": bool(only_approved),
        "limit": shown,
    }


def _review_status(raw: str) -> Literal["confirmed", "needs_look"]:
    match raw:
        case "pending":
            return "needs_look"
        case "asserted" | "applied" | "approved" | "active" | "ok" | "":
            return "confirmed"
        case "rejected":
            return "needs_look"
        case _ as other:
            return "needs_look" if other == "pending" else "confirmed"


def _in_window(when: str | None, since: str, until: str) -> bool:
    if not when:
        return True
    if since and when < since:
        return False
    if until and when > until:
        return False
    return True


def _apply_fields(fields: dict[str, Any], include: list[str], exclude: list[str]) -> dict[str, Any]:
    cleaned = {key: value for key, value in fields.items() if not _is_secret_key(str(key))}
    if include:
        wanted = set(include)
        cleaned = {key: value for key, value in cleaned.items() if key in wanted}
    if exclude:
        skip = set(exclude)
        cleaned = {key: value for key, value in cleaned.items() if key not in skip}
    return cleaned


def _matches_query(record: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    needle = query.casefold()
    haystacks = [
        str(record.get("title") or ""),
        str(record.get("summary") or ""),
        str(record.get("type") or ""),
        str(record.get("type_label") or ""),
        str(record.get("family_label") or ""),
    ]
    fields = record.get("fields") or {}
    haystacks.extend(f"{key} {value}" for key, value in fields.items())
    return any(needle in chunk.casefold() for chunk in haystacks)


def _keep_status(record: dict[str, Any], gate: ReviewGate, only_approved: bool) -> bool:
    status = str(record.get("status") or "confirmed")
    if only_approved and status != "confirmed":
        return False
    match gate:
        case "all":
            return True
        case "confirmed":
            return status == "confirmed"
        case "needs_look":
            return status == "needs_look"
        case _ as unreachable:
            raise AssertionError(f"unhandled review gate {unreachable}")


def _keep_type(record: dict[str, Any], types: list[str]) -> bool:
    if not types:
        return True
    wanted = set(types)
    return str(record.get("type") or "") in wanted


def _record(
    *,
    family: TrainFamily,
    rec_id: str,
    rec_type: str,
    title: str,
    summary: str,
    status_raw: str,
    when: str | None,
    fields: dict[str, Any],
    include: list[str],
    exclude: list[str],
) -> dict[str, Any]:
    review = _review_status(status_raw)
    cleaned = _apply_fields(_scrub(fields), include, exclude)
    return {
        "id": rec_id,
        "family": family,
        "family_label": family_label(family),
        "type": rec_type,
        "type_label": title_case(rec_type),
        "title": title,
        "summary": summary,
        "status": review,
        "status_label": "Confirmed" if review == "confirmed" else "Needs a look",
        "when": when,
        "fields": cleaned,
    }
