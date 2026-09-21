"""Auth flow tests.

All of these commit real rows, so they require the Postgres container to
be running (`make db-up`) and the schema migrated (`make migrate`).
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.security import create_token
from app.main import app

client = TestClient(app)

PASSWORD = "Passw0rd!"


def _register_and_login() -> dict:
    """Create a fresh user and return its token pair.

    Emails are unique per call because users.email is uniquely indexed and
    these tests write committed rows.
    """
    email = f"jwt-{uuid.uuid4()}@example.com"
    created = client.post(
        "/api/v1/users/",
        json={"name": "Ada", "email": email, "password": PASSWORD},
    )
    assert created.status_code == 201

    resp = client.post("/api/v1/users/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return {"email": email, **resp.json()}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# success paths
def test_login_returns_token_pair():
    body = _register_and_login()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_returns_user_name_and_email():
    body = _register_and_login()
    assert body["user"]["email"] == body["email"]
    assert body["user"]["name"] == "Ada"
    # UserRead excludes it; assert here so a future schema change cannot
    # start leaking the hash through the login response.
    assert "password" not in body["user"]


def test_refresh_returns_tokens_only():
    """/refresh has no user context, so it stays a bare TokenPair."""
    body = _register_and_login()
    resp = client.post("/api/v1/users/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 200
    assert "user" not in resp.json()


def test_me_returns_current_user():
    body = _register_and_login()
    resp = client.get("/api/v1/users/me", headers=_auth(body["access_token"]))
    assert resp.status_code == 200
    assert resp.json()["email"] == body["email"]
    assert "password" not in resp.json()


def test_refresh_rotates_tokens():
    body = _register_and_login()
    resp = client.post("/api/v1/users/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 200
    # jti is a fresh uuid per mint, so rotated tokens differ even within
    # the same second despite iat/exp having 1s resolution.
    assert resp.json()["access_token"] != body["access_token"]
    assert resp.json()["refresh_token"] != body["refresh_token"]


def test_logout_returns_204():
    body = _register_and_login()
    resp = client.post("/api/v1/users/logout", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 204
    assert not resp.content


# failure paths
def test_login_wrong_password():
    body = _register_and_login()
    resp = client.post(
        "/api/v1/users/login",
        json={"email": body["email"], "password": "Wr0ngPass!"},
    )
    assert resp.status_code == 401


def test_me_without_header():
    assert client.get("/api/v1/users/me").status_code == 401


def test_me_with_garbage_token():
    assert client.get("/api/v1/users/me", headers=_auth("not-a-jwt")).status_code == 401


def test_me_rejects_refresh_token():
    body = _register_and_login()
    resp = client.get("/api/v1/users/me", headers=_auth(body["refresh_token"]))
    assert resp.status_code == 401


def test_refresh_token_is_single_use():
    body = _register_and_login()
    first = client.post("/api/v1/users/refresh", json={"refresh_token": body["refresh_token"]})
    assert first.status_code == 200

    replay = client.post("/api/v1/users/refresh", json={"refresh_token": body["refresh_token"]})
    assert replay.status_code == 401


def test_refresh_after_logout():
    body = _register_and_login()
    assert (
        client.post("/api/v1/users/logout", json={"refresh_token": body["refresh_token"]})
    ).status_code == 204

    resp = client.post("/api/v1/users/refresh", json={"refresh_token": body["refresh_token"]})
    assert resp.status_code == 401


def test_me_with_expired_token():
    # Negative delta puts exp in the past, so no sleeping.
    expired, _, _ = create_token(str(uuid.uuid4()), "access", timedelta(minutes=-5))
    assert client.get("/api/v1/users/me", headers=_auth(expired)).status_code == 401
