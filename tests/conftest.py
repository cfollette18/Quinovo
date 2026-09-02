from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from quinovo.api.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=tmp_path / "test.sqlite")
    with TestClient(app) as test_client:
        yield test_client
