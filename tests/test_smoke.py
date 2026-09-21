from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_db():
    """Requires the Postgres container to be running (`make db-up`)."""
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json()["db"] == "reachable"
