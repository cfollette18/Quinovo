from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quinovo.api.app import create_app

EXAMPLE_PACK = Path(__file__).parent / "fixtures" / "example"
CLINIC_PACK = Path(__file__).parent / "fixtures" / "clinic"


@pytest.fixture(autouse=True)
def isolate_llm_settings(tmp_path, monkeypatch):
    path = tmp_path / "isolated-llm.yaml"
    monkeypatch.setattr("quinovo.llm.settings.SETTINGS_PATH", path)
    from quinovo.llm.settings import LLMSettings, save_settings

    save_settings(LLMSettings(api_key="", enabled=True, model="MiniMax-M3"))


@pytest.fixture(autouse=True)
def disable_langfuse_in_tests(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")


@pytest.fixture(autouse=True)
def isolate_session_data(tmp_path, monkeypatch):
    monkeypatch.setattr("quinovo.apps.session.DATA_DIR", tmp_path / "data")


@pytest.fixture(autouse=True)
def isolate_chats(tmp_path, monkeypatch):
    monkeypatch.setattr("quinovo.chat.sessions.CHATS_DIR", tmp_path / "chats")


@pytest.fixture
def client(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    app = create_app(pack_dir=pack, db_path=tmp_path / "test.sqlite")
    with TestClient(app) as test_client:
        yield test_client
