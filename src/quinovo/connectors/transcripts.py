"""Ingest agent transcripts (Cursor jsonl, Hermes jsonl) as Conversation objects.

Tick pulls this source automatically. Each file becomes one Conversation linked
to a Topic inferred from the file path, so every agent chat lands in the world
even when the agent forgets ``save_turn``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from glob import glob
from pathlib import Path
from typing import Any

from quinovo.connectors.base import ConnectorError, SourceRecord, SourceRun
from quinovo.engine.store import ObjectStore

_SUMMARY_LIMIT = 4000

_DEFAULT_PATH_TOPICS = {
    "cretex-automation": "workflows",
    "cretex": "cretex",
    "Quinovo": "quinovo",
    "quinovo": "quinovo",
    "jig": "jig",
    "orzo": "orzo",
}


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return ""


def _user_query(text: str) -> str:
    marker = "<user_query>"
    end = "</user_query>"
    if marker in text and end in text:
        start = text.index(marker) + len(marker)
        return text[start : text.index(end, start)].strip()
    return text.strip()


def parse_transcript(path: Path) -> dict[str, Any] | None:
    """Turn one jsonl transcript into Conversation properties."""
    queries: list[str] = []
    last_assistant = ""
    turn_index = 0
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "")
        message = row.get("message") if isinstance(row.get("message"), dict) else row
        text = _text_from_content(message.get("content") if isinstance(message, dict) else None)
        if role == "user":
            query = _user_query(text)
            if query:
                queries.append(query)
                turn_index += 1
        elif role == "assistant" and text:
            last_assistant = text.split("\n", 1)[0].strip()
    if not queries and not last_assistant:
        return None
    session_id = path.stem
    summary_bits = [" ".join(queries[:8])]
    if last_assistant:
        summary_bits.append(last_assistant)
    summary = " — ".join(part for part in summary_bits if part)[:_SUMMARY_LIMIT]
    recorded_at = ""
    try:
        recorded_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        recorded_at = ""
    return {
        "id": f"cursor:{session_id}:0",
        "session_id": f"cursor:{session_id}",
        "turn_index": turn_index or 0,
        "summary": summary or session_id,
        "recorded_at": recorded_at,
        "role": "transcript",
    }


def topic_for_path(path: Path, mapping: dict[str, str], default: str) -> str:
    text = str(path)
    ranked = sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
    for needle, topic in ranked:
        if needle and needle in text:
            return topic
    return default


class TranscriptsSource:
    """Glob jsonl agent transcripts and upsert them as Conversation objects."""

    kind = "transcripts"

    def run(self, store: ObjectStore, record: SourceRecord) -> SourceRun:
        globs = record.config.get("globs") or record.config.get("glob")
        if isinstance(globs, str):
            patterns = [globs]
        elif isinstance(globs, list):
            patterns = [str(item) for item in globs]
        else:
            raise ConnectorError("transcripts source needs glob or globs")
        mapping = record.config.get("path_topics") or {}
        if not isinstance(mapping, dict):
            raise ConnectorError("path_topics must be a mapping")
        path_topics = {str(key): str(value) for key, value in mapping.items()}
        if not path_topics:
            path_topics = dict(_DEFAULT_PATH_TOPICS)
        default_topic = str(record.config.get("default_topic") or "quinovo")
        files: list[Path] = []
        seen: set[str] = set()
        for pattern in patterns:
            for match in glob(pattern, recursive=True):
                if match in seen:
                    continue
                seen.add(match)
                files.append(Path(match))
        upserted: list[dict[str, Any]] = []
        for path in files:
            props = parse_transcript(path)
            if props is None:
                continue
            topic_id = topic_for_path(path, path_topics, default_topic)
            if store.get_object("Topic", topic_id) is None:
                store.upsert_object(
                    "Topic",
                    {"id": topic_id, "name": topic_id.replace("-", " ").title(), "status": "active"},
                    source="funnel",
                )
            existing = store.get_object("Conversation", props["id"])
            if existing is not None and existing.properties.get("summary") == props["summary"]:
                continue
            obj = store.upsert_object("Conversation", props, source="funnel")
            store.add_link(
                "conversation_in_topic",
                "Conversation",
                obj.id,
                "Topic",
                topic_id,
            )
            upserted.append({"type": obj.object_type, "id": obj.id, "version": obj.version})
        return SourceRun(
            upserted=upserted,
            detail=f"{len(upserted)} transcripts from {len(files)} files",
        )
