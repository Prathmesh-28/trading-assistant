"""server.py — auth middleware, login, and the brute-force damper.

The env MUST be pinned before `import server`: server.py builds its Settings
(and the session token) at import time. conftest.py already exports these,
but they are re-asserted here so the module is self-contained. The engine
runs on the synthetic feed inside TestClient's lifespan — everything below
must tolerate it ticking in the background.
"""

import os

os.environ["JOURNAL_PATH"] = "/tmp/test_auth_ci.db"
os.environ["AUTH_USERNAME"] = "u"
os.environ["AUTH_PASSWORD"] = "p"
os.environ["GROWW_API_KEY"] = ""
os.environ["GROWW_API_SECRET"] = ""
os.environ["GROWW_TOTP_SECRET"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["DATABASE_URL"] = ""

if os.path.exists("/tmp/test_auth_ci.db"):
    os.remove("/tmp/test_auth_ci.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402  (env above must win before this import)

GOOD = {"username": "u", "password": "p"}
BAD = {"username": "u", "password": "wrong"}


@pytest.fixture(scope="module")
def client():
    # `with` drives the lifespan: the engine task starts on entry (synthetic
    # feed — no creds in env) and is cancelled cleanly on exit.
    with TestClient(server.app) as c:
        yield c


def _login(client):
    r = client.post("/api/login", json=GOOD)
    assert r.status_code == 200
    return r.json()["token"]


def test_health_is_public_and_reports_mode(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "mode" in body
    assert body["mode"] in ("SYNTHETIC", "LIVE")


def test_status_requires_token(client):
    assert client.get("/api/status").status_code == 401


def test_login_wrong_creds_401(client):
    assert client.post("/api/login", json=BAD).status_code == 401


def test_login_right_creds_returns_token(client):
    r = client.post("/api/login", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    assert body.get("token")
    assert "mode" in body


def test_status_ok_with_bearer_token(client):
    token = _login(client)
    r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_garbage_token_still_401(client):
    r = client.get("/api/status", headers={"Authorization": "Bearer not-the-token"})
    assert r.status_code == 401


def test_sixth_bad_login_from_same_client_is_429(client):
    _login(client)  # a successful login resets this client's failure counter
    for i in range(5):
        r = client.post("/api/login", json=BAD)
        assert r.status_code == 401, f"attempt {i + 1} should still be 401"
    assert client.post("/api/login", json=BAD).status_code == 429
    # even the RIGHT password is throttled while locked out
    assert client.post("/api/login", json=GOOD).status_code == 429
