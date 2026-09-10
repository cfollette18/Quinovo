from __future__ import annotations

from quinovo.llm.engine import LLMEngine, LLMError
from quinovo.llm.hermes import import_hermes
from quinovo.llm.settings import LLMSettings, load_settings, save_settings


def test_import_hermes_reads_model_url_and_key(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        "model:\n"
        "  provider: minimax\n"
        "  default: MiniMax-M3\n"
        "  base_url: https://api.minimax.io/anthropic\n",
        encoding="utf-8",
    )
    (home / ".env").write_text("MINIMAX_API_KEY=sk-test-secret\n", encoding="utf-8")
    settings = import_hermes(home)
    assert settings.provider == "minimax"
    assert settings.model == "MiniMax-M3"
    assert settings.base_url == "https://api.minimax.io/anthropic"
    assert settings.protocol == "anthropic"
    assert settings.api_key == "sk-test-secret"
    public = settings.public()
    assert public["api_key_set"] is True
    assert public["api_key_tail"] == "cret"
    assert "sk-test-secret" not in str(public)


def test_settings_page_hides_key_and_imports_hermes(client, tmp_path, monkeypatch):
    monkeypatch.setattr("quinovo.llm.settings.SETTINGS_PATH", tmp_path / "llm.yaml")
    save_settings(
        LLMSettings(
            provider="minimax",
            model="MiniMax-M3",
            base_url="https://api.minimax.io/anthropic",
            api_key="super-secret-key-do-not-leak",
            protocol="anthropic",
            source="hermes",
        )
    )
    page = client.get("/settings")
    assert page.status_code == 200
    assert "Settings" in page.text
    assert "href=\"/settings\"" in page.text
    assert "MiniMax-M3" in page.text
    assert "minimax" in page.text
    assert "https://api.minimax.io/anthropic" in page.text
    assert "Import from Hermes" in page.text
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
    assert "super-secret-key-do-not-leak" not in page.text
    payload = client.get("/settings.json").json()
    assert payload["model"] == "MiniMax-M3"
    assert payload["api_key_set"] is True
    assert "api_key" not in payload
    assert "super-secret-key-do-not-leak" not in str(payload)
    assert "enabled" in payload["tracing"]
    assert "environment" in payload["tracing"]
    assert payload["tracing"]["disagreement_dataset"]


def test_import_from_hermes_form(client, tmp_path, monkeypatch):
    monkeypatch.setattr("quinovo.llm.settings.SETTINGS_PATH", tmp_path / "llm.yaml")
    imported = LLMSettings(
        provider="minimax",
        model="MiniMax-M3",
        base_url="https://api.minimax.io/anthropic",
        api_key="imported-secret-value",
        protocol="anthropic",
        source="hermes",
    )
    monkeypatch.setattr("quinovo.llm.hermes.import_hermes", lambda home=None: imported)
    response = client.post("/settings", data={"intent": "import_hermes"}, follow_redirects=False)
    assert response.status_code == 303
    saved = load_settings()
    assert saved.model == "MiniMax-M3"
    assert saved.api_key == "imported-secret-value"
    page = client.get("/settings")
    assert "imported-secret-value" not in page.text


def test_anthropic_engine_posts_messages(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [{"type": "text", "text": "ok"}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("quinovo.llm.engine.httpx.post", fake_post)
    engine = LLMEngine(
        LLMSettings(
            provider="minimax",
            model="MiniMax-M3",
            base_url="https://api.minimax.io/anthropic",
            api_key="k",
            protocol="anthropic",
        )
    )
    assert engine.complete("hi") == "ok"
    assert captured["url"] == "https://api.minimax.io/anthropic/v1/messages"
    assert captured["headers"]["x-api-key"] == "k"
    assert captured["json"]["model"] == "MiniMax-M3"


def test_engine_requires_key():
    engine = LLMEngine(LLMSettings(api_key=""))
    try:
        engine.complete("hi")
    except LLMError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("expected LLMError")
