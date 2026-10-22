from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_root_advertises_public_backend_paths() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": settings.app_name,
        "status": "ok",
        "health": "/health",
        "readiness": "/ready",
        "docs": "/docs",
        "api_prefix": "/api",
    }


def test_health_supports_get_and_head() -> None:
    client = TestClient(app)

    get_response = client.get("/health")
    head_response = client.head("/health")
    root_head = client.head("/")

    assert get_response.status_code == 200
    assert get_response.json() == {"status": "ok"}
    assert head_response.status_code == 200
    assert root_head.status_code == 200
