"""LLM settings. Keys stay on disk under .data, never in the pack YAML."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from quinovo.workspace import ROOT

SETTINGS_PATH = ROOT / ".data" / "llm.yaml"


@dataclass
class LLMSettings:
    provider: str = "minimax"
    model: str = "MiniMax-M3"
    base_url: str = "https://api.minimax.io/anthropic"
    api_key: str = ""
    enabled: bool = True
    protocol: str = "anthropic"
    source: str = "manual"

    def public(self) -> dict[str, Any]:
        key = self.api_key.strip()
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "protocol": self.protocol,
            "enabled": self.enabled,
            "source": self.source,
            "api_key_set": bool(key),
            "api_key_tail": key[-4:] if len(key) >= 4 else "",
        }

    def ready(self) -> bool:
        return self.enabled and bool(self.api_key.strip()) and bool(self.model.strip())


def _path() -> Path:
    return SETTINGS_PATH


def load_settings() -> LLMSettings:
    path = _path()
    if not path.exists():
        return LLMSettings()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return LLMSettings()
    known = {k: raw[k] for k in LLMSettings.__dataclass_fields__ if k in raw}
    return LLMSettings(**known)


def ensure_settings() -> LLMSettings:
    """Load saved settings, or import Hermes once and persist."""
    if _path().exists():
        return load_settings()
    from quinovo.llm.hermes import import_hermes

    imported = import_hermes()
    save_settings(imported)
    return imported


def save_settings(settings: LLMSettings) -> Path:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def update_settings(
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enabled: bool | None = None,
    protocol: str | None = None,
    source: str | None = None,
) -> LLMSettings:
    current = load_settings()
    if provider is not None and provider.strip():
        current.provider = provider.strip()
    if model is not None and model.strip():
        current.model = model.strip()
    if base_url is not None and base_url.strip():
        current.base_url = base_url.strip().rstrip("/")
    if api_key is not None and api_key.strip():
        current.api_key = api_key.strip()
    if enabled is not None:
        current.enabled = enabled
    if protocol is not None and protocol.strip():
        current.protocol = protocol.strip()
    elif base_url is not None and base_url.strip():
        current.protocol = "anthropic" if "anthropic" in current.base_url else "openai"
    if source is not None:
        current.source = source
    save_settings(current)
    return current
