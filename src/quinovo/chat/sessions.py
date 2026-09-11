"""Chat transcripts on disk under .data/chats. Not a second database."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quinovo.workspace import ROOT

CHATS_DIR = ROOT / ".data" / "chats"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _dir() -> Path:
    path = CHATS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class ChatSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[dict[str, Any]] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def new_session(title: str = "New chat") -> ChatSession:
    stamp = _now()
    return ChatSession(
        id=uuid.uuid4().hex[:16],
        title=title.strip() or "New chat",
        created_at=stamp,
        updated_at=stamp,
    )


def _path(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
    if not safe or safe != session_id:
        raise KeyError(session_id)
    return _dir() / f"{safe}.json"


def save_session(session: ChatSession) -> ChatSession:
    session.updated_at = _now()
    path = _path(session.id)
    path.write_text(json.dumps(session.public(), indent=2), encoding="utf-8")
    return session


def get_session(session_id: str) -> ChatSession:
    path = _path(session_id)
    if not path.is_file():
        raise KeyError(session_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ChatSession(
        id=str(raw.get("id") or session_id),
        title=str(raw.get("title") or "Chat"),
        created_at=str(raw.get("created_at") or _now()),
        updated_at=str(raw.get("updated_at") or _now()),
        messages=list(raw.get("messages") or []),
    )


def list_sessions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _dir().glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "id": str(raw.get("id") or path.stem),
                "title": str(raw.get("title") or "Chat"),
                "created_at": str(raw.get("created_at") or ""),
                "updated_at": str(raw.get("updated_at") or ""),
            }
        )
    rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return rows


def delete_session(session_id: str) -> None:
    path = _path(session_id)
    if path.is_file():
        path.unlink()


def title_from_text(text: str) -> str:
    line = " ".join(text.strip().split())
    if len(line) > 48:
        return line[:45].rstrip() + "…"
    return line or "New chat"
