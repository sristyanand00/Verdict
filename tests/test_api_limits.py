"""Limits for a public server: private uploads, time limit, rate and load limits, plain errors."""

import threading
import time

from fastapi.testclient import TestClient

from tests.test_api import as_admin, ask, block, env, login_as, signup  # noqa: F401  (env is a fixture)
from verdict.api.auth import RateLimiter

CSV = ("Sales.csv", b"City,Amount\nPune,10\nDelhi,5\n", "text/csv")


def other_user(client, email="eve@test.local"):
    c = TestClient(client.app)
    login_as(c, signup(c, email, name="Eve"))
    return c


def upload(client):
    r = client.post("/api/databases/upload", files={"file": CSV})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# -- uploads ---------------------------------------------------------------------

def test_an_upload_is_private_to_its_owner(env, tmp_path, monkeypatch):
    monkeypatch.setenv("VERDICT_UPLOADS_ROOT", str(tmp_path / "uploads"))
    client, w, _ = env
    up = upload(client)

    eve = other_user(client)
    assert up not in [d["id"] for d in eve.get("/api/databases").json()]
    assert eve.get(f"/api/databases/{up}/schema").status_code == 404
    assert eve.post("/api/sql/run", json={"database_id": up, "sql": "SELECT 1"}).status_code == 404
    assert eve.get("/api/knowledge", params={"database_id": up}).status_code == 404
    r = eve.post("/api/ask", json={"question": "Total?", "database_id": up, "model": "fixed"})
    assert r.status_code == 404

    assert up in [d["id"] for d in as_admin(client).get("/api/databases").json()]
    # Health lists only the preloaded databases.
    assert up not in client.get("/api/health").json()["databases"]


def test_uploads_can_be_turned_off(env):
    client, _, state = env
    state.uploads_enabled = False
    r = client.post("/api/databases/upload", files={"file": CSV})
    assert r.status_code == 403 and "turned off" in r.json()["detail"]


def test_old_uploads_are_deleted(env, tmp_path, monkeypatch):
    monkeypatch.setenv("VERDICT_UPLOADS_ROOT", str(tmp_path / "uploads"))
    client, _, state = env
    up = upload(client)
    path = state.store.get_database(up)["path"]
    state.store._run("UPDATE databases SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (up,))
    state.upload_ttl_hours = 24
    assert up not in [d["id"] for d in client.get("/api/databases").json()]
    assert state.store.get_database(up) is None
    from pathlib import Path
    assert not Path(path).exists()


# -- asking ------------------------------------------------------------------------

def slow_writers(state, seconds):
    real = state.writer_factory

    def make(model):
        inner = real(model)

        class Slow:
            def write(self, prompt, n):
                time.sleep(seconds)
                return inner.write(prompt, n)
        return Slow()
    state.writer_factory = make


def test_a_slow_ask_is_stopped_and_not_charged(env):
    client, w, state = env
    slow_writers(state, 1.5)
    state.ask_timeout_s = 0.3
    w.replies = [block("SELECT 1")] * 8
    r = client.post("/api/ask", json={"question": "How many?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 504 and "not charged" in r.json()["detail"]
    assert client.get("/api/me").json()["credits"]["balance"] == 1000
    assert client.get("/api/asks").json() == []


def test_too_many_asks_at_once_wait_then_get_busy(env):
    client, w, state = env
    slow_writers(state, 1.0)
    state.ask_slots = threading.BoundedSemaphore(1)
    state.queue_wait_s = 0.1
    w.replies = [block("SELECT 1")] * 8
    token = client.headers["Authorization"]
    codes = []

    def go(q):
        c = TestClient(client.app)
        c.headers["Authorization"] = token
        codes.append(c.post("/api/ask", json={"question": q, "database_id": "tiny", "model": "fixed"}).status_code)

    first = threading.Thread(target=go, args=("one?",))
    first.start()
    time.sleep(0.3)
    go("two?")
    first.join()
    assert sorted(codes) == [200, 503]


def test_asks_per_minute_are_limited(env):
    client, w, state = env
    state.ask_limiter = RateLimiter(2, message="slow down")
    w.replies = [block("SELECT 1")] * 8
    ask(client, "a?")
    ask(client, "b?")
    r = client.post("/api/ask", json={"question": "c?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 429 and r.json()["detail"] == "slow down"
    # Another user has their own limit.
    eve = other_user(client)
    assert eve.post("/api/ask", json={"question": "d?", "database_id": "tiny", "model": "fixed"}).status_code == 200


def test_model_errors_do_not_show_server_details(env):
    client, w, _ = env
    w.down = True
    r = client.post("/api/ask", json={"question": "How many?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "connection refused" not in detail and "http" not in detail.lower()
    assert "not charged" in detail


# -- shared settings -----------------------------------------------------------------

def test_only_the_provider_changes_shared_settings(env):
    client, _, _ = env
    assert client.put("/api/settings", json={"second_model": True}).status_code == 403
    assert as_admin(client).put("/api/settings", json={"second_model": True}).status_code == 200
