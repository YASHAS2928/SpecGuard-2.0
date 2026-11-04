from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_api.main import app as mock_app


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173"])
def test_admin_version_preflight_allows_frontend_origins(origin: str) -> None:
    with TestClient(mock_app) as client:
        response = client.options(
            "/admin/version",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_admin_version_preflight_rejects_unlisted_origin() -> None:
    with TestClient(mock_app) as client:
        response = client.options(
            "/admin/version",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert "access-control-allow-origin" not in response.headers
