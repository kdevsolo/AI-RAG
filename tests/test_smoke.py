import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # A context manager, not a bare TestClient(app): only this form runs the
    # app's lifespan (see main.py) — without it, startup code (e.g.
    # connecting to Temporal) silently never executes and these tests would
    # give false confidence about app startup actually working.
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_db(client):
    """Requires the Postgres container to be running (`make db-up`)."""
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json()["db"] == "reachable"
