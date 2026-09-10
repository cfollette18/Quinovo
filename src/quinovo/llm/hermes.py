"""Read provider, model, base URL, and API key from a local Hermes install."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from quinovo.llm.settings import LLMSettings

HERMES_HOME = Path.home() / ".hermes"
KEY_ENV = {
    "minimax": "MINIMAX_API_KEY",
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _parse_env_file(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        value = value.strip().strip("'").strip('"')
        if name:
            found[name] = value
    return found


def _key_for(provider: str, env_files: list[Path]) -> str:
    env_name = KEY_ENV.get(provider, f"{provider.upper().replace('-', '_')}_API_KEY")
    from_os = os.environ.get(env_name, "").strip()
    if from_os:
        return from_os
    for path in env_files:
        value = _parse_env_file(path).get(env_name, "").strip()
        if value:
            return value
    return ""


def import_hermes(home: Path | None = None) -> LLMSettings:
    root = home or HERMES_HOME
    config_path = root / "config.yaml"
    provider = "minimax"
    model = "MiniMax-M3"
    base_url = "https://api.minimax.io/anthropic"
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        block = raw.get("model") if isinstance(raw, dict) else None
        if isinstance(block, dict):
            provider = str(block.get("provider") or provider)
            model = str(block.get("default") or block.get("model") or model)
            base_url = str(block.get("base_url") or base_url).rstrip("/")
        auth_path = root / "auth.json"
        if auth_path.exists():
            import json

            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            pool = (auth.get("credential_pool") or {}).get(provider) or []
            if pool and isinstance(pool, list) and isinstance(pool[0], dict):
                listed = str(pool[0].get("base_url") or "").rstrip("/")
                if listed:
                    base_url = listed
    api_key = _key_for(provider, [root / ".env", root / "profiles" / "vera" / ".env"])
    protocol = "anthropic" if "anthropic" in base_url else "openai"
    return LLMSettings(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        enabled=True,
        protocol=protocol,
        source="hermes",
    )
