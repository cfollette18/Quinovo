from __future__ import annotations

from fastapi.testclient import TestClient

from quinovo.apps.logo_mocks import LOGO_MOCKS


def test_logo_mocks_page_lists_all_images(client: TestClient):
    page = client.get("/logo-mocks")
    assert page.status_code == 200
    assert "json-panel" not in page.text
    assert "<pre" not in page.text
    assert "Logo mocks" in page.text
    assert 'href="/"' in page.text
    for mock in LOGO_MOCKS:
        assert mock.name in page.text
        assert f"/assets/logo-mocks/{mock.filename}" in page.text


def test_logo_mock_images_are_served(client: TestClient):
    for mock in LOGO_MOCKS:
        path = f"/assets/logo-mocks/{mock.filename}"
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
        ctype = response.headers["content-type"]
        assert ctype in {"image/png", "image/jpeg"}, (path, ctype)
        assert response.content[:3] in {b"\x89PN", b"\xff\xd8\xff"}
