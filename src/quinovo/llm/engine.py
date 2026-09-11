"""Main LLM engine. MiniMax is Anthropic-compatible at api.minimax.io/anthropic."""

from __future__ import annotations

from typing import Any

import httpx

from quinovo.llm.disagreement import disagreement_dataset_name
from quinovo.llm.eval_dataset import eval_dataset_name
from quinovo.llm.settings import LLMSettings, ensure_settings, load_settings
from quinovo.llm.tracing import (
    observe_generation,
    tracing_enabled,
    tracing_environment,
    usage_from_provider,
)


class LLMError(Exception):
    """Provider rejected the completion."""


class LLMEngine:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        feature: str = "generate-completion",
    ) -> str:
        if not self.settings.ready():
            raise LLMError("LLM is not configured")

        def run() -> tuple[str, dict[str, int], dict[str, Any]]:
            match self.settings.protocol:
                case "anthropic":
                    return self._anthropic(prompt, max_tokens)
                case "openai":
                    return self._openai(prompt, max_tokens)
                case _ as unreachable:
                    raise LLMError(f"unhandled protocol {unreachable!r}")

        return observe_generation(
            name=feature,
            model=self.settings.model,
            protocol=self.settings.protocol,
            provider=self.settings.provider,
            prompt=prompt,
            run=run,
        )

    def _anthropic(self, prompt: str, max_tokens: int) -> tuple[str, dict[str, int], dict[str, Any]]:
        url = f"{self.settings.base_url.rstrip('/')}/v1/messages"
        response = httpx.post(
            url,
            headers={
                "x-api-key": self.settings.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.settings.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        if response.status_code >= 400:
            raise LLMError(f"{response.status_code}: {response.text[:400]}")
        data = response.json()
        chunks = data.get("content") or []
        texts = [
            item.get("text", "")
            for item in chunks
            if isinstance(item, dict) and item.get("type") in (None, "text")
        ]
        if not texts and isinstance(data.get("content"), str):
            text = str(data["content"])
        else:
            text = "".join(texts).strip()
        return text, usage_from_provider("anthropic", data), data

    def _openai(self, prompt: str, max_tokens: int) -> tuple[str, dict[str, int], dict[str, Any]]:
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        response = httpx.post(
            url,
            headers={
                "authorization": f"Bearer {self.settings.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.settings.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        if response.status_code >= 400:
            raise LLMError(f"{response.status_code}: {response.text[:400]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return "", usage_from_provider("openai", data), data
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        return text, usage_from_provider("openai", data), data


def engine_from_settings(settings: LLMSettings | None = None) -> LLMEngine:
    if settings is not None:
        return LLMEngine(settings)
    return LLMEngine(ensure_settings())


def status_payload(settings: LLMSettings | None = None) -> dict[str, Any]:
    item = settings or load_settings()
    public = item.public()
    public["ready"] = item.ready()
    public["tracing"] = {
        "enabled": tracing_enabled(),
        "environment": tracing_environment(),
        "disagreement_dataset": disagreement_dataset_name(),
        "eval_dataset": eval_dataset_name(),
    }
    return public
