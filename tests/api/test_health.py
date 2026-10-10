from fastapi.testclient import TestClient

from applications.api.main import app
from packages.core.db.session import engine


def test_health_reports_api_database_and_storage():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["services"]["api"]["status"] == "ok"
    assert body["services"]["database"]["status"] in {"ok", "unavailable"}
    assert body["services"]["storage"]["status"] in {"ok", "unavailable"}


def test_vercel_health_reports_ephemeral_filesystem_storage(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["storage"]["persistence"] == "ephemeral"
    expected_database_persistence = "ephemeral" if engine.dialect.name == "sqlite" else "configured"
    assert body["services"]["database"]["persistence"] == expected_database_persistence


def test_vercel_health_reports_connected_blob_storage(monkeypatch):
    class HealthyBlobStorage:
        driver = "vercel_blob"
        persistence = "durable"

        def check_health(self):
            return None

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(
        "applications.api.main.get_artifact_storage",
        lambda: HealthyBlobStorage(),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["services"]["storage"] == {
        "status": "ok",
        "driver": "vercel_blob",
        "persistence": "durable",
    }
