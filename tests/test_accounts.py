"""Accounts, credits, the provider panel, and who can see what."""

import sqlite3
import threading
import time

from fastapi.testclient import TestClient

from tests.test_api import ask, block, env, login_as, signup  # noqa: F401  (env is a fixture)
from verdict.store.db import Store

ADMIN = {"email": "admin@test.local", "password": "admin-password-1"}


def admin_client(state):
    from verdict.api.main import create_app

    c = TestClient(create_app(state, frontend_dist=None))
    r = c.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    login_as(c, r.json()["token"])
    return c


def my_id(client):
    return client.get("/api/me").json()["user"]["id"]


def set_balance(state, client, value):
    """Use the provider panel to bring a user's balance to ``value``."""
    admin = admin_client(state)
    uid = my_id(client)
    have = client.get("/api/me").json()["credits"]["balance"]
    if value != have:
        r = admin.post(f"/api/admin/users/{uid}/credits", json={"amount": value - have, "note": "test"})
        assert r.status_code == 200, r.text


# -- signup, login, logout ---------------------------------------------------------

def test_signup_login_logout(env):
    client, _, _ = env
    token = signup(client, "Bo@Test.local", name="Bo")
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["user"]["role"] == "analyst" and me["user"]["email"] == "Bo@Test.local"
    assert "password" not in str(me) and "hash" not in str(me)

    # Same email, other case: taken.
    r = client.post("/api/auth/signup", json={"name": "x", "email": "bo@test.LOCAL", "password": "12345678"})
    assert r.status_code == 409
    r = client.post("/api/auth/signup", json={"name": "x", "email": "new@test.local", "password": "short"})
    assert r.status_code == 400

    assert client.post("/api/auth/login", json={"email": "bo@test.local", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@test.local", "password": "password-123"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "bo@test.local", "password": "password-123"})
    assert r.status_code == 200 and r.json()["me"]["user"]["name"] == "Bo"

    t2 = r.json()["token"]
    h = {"Authorization": f"Bearer {t2}"}
    assert client.post("/api/auth/logout", headers=h).json() == {"ok": True}
    assert client.get("/api/me", headers=h).status_code == 401


def test_routes_need_login_except_health(env):
    client, _, _ = env
    del client.headers["Authorization"]
    assert client.get("/api/health").status_code == 200
    for path in ("/api/me", "/api/asks", "/api/review", "/api/databases", "/api/saved", "/api/models"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/ask", json={"question": "x"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer made-up"}).status_code == 401


def test_me_shape_and_starting_credits(env):
    client, _, state = env
    me = client.get("/api/me").json()
    assert me["credits"] == {"balance": 1000, "used_total": 0, "used_this_month": 0}
    assert me["prices"] == {"ask": 1, "arena_outside_model": 1}
    usage = client.get("/api/me/usage").json()
    assert len(usage) == 1 and usage[0]["kind"] == "grant" and usage[0]["note"] == "Starting credits"
    assert usage[0]["amount"] == 1000 and usage[0]["balance_after"] == 1000


# -- credits on ask ------------------------------------------------------------------

def test_ask_charges_one_credit(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    r = ask(client, "How many students?")
    me = client.get("/api/me").json()["credits"]
    assert me == {"balance": 999, "used_total": 1, "used_this_month": 1}
    row = client.get("/api/me/usage").json()[0]
    assert row["kind"] == "ask" and row["amount"] == -1 and row["balance_after"] == 999
    assert row["ask_id"] == r["ask_id"] and row["question"] == "How many students?"


def test_review_and_reject_are_charged(env):
    client, w, _ = env
    w.replies = [block("SELECT 1"), block("SELECT 2"), block("SELECT 3"), block("SELECT 4")]
    assert ask(client, "anything?")["level"] == "reject"
    assert client.get("/api/me").json()["credits"]["balance"] == 999


def test_no_credits_is_402_and_runs_nothing(env):
    client, w, state = env
    set_balance(state, client, 0)
    before = len(w.prompts)
    r = client.post("/api/ask", json={"question": "How many students?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 402
    assert r.json()["detail"] == "You have no credits left. Ask the provider for more."
    assert len(w.prompts) == before
    assert client.get("/api/asks").json() == []


def test_server_failure_is_not_charged(env):
    client, w, _ = env
    w.down = True
    r = client.post("/api/ask", json={"question": "How many students?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 503
    assert client.get("/api/me").json()["credits"]["balance"] == 1000
    assert [e["kind"] for e in client.get("/api/me/usage").json()] == ["grant"]


def test_two_asks_at_once_cannot_go_below_zero(env):
    client, w, state = env
    set_balance(state, client, 1)
    token = client.headers["Authorization"]

    # A slow model, so both asks are running at the same moment.
    real = state.writer_factory

    def slow(model):
        inner = real(model)

        class Slow:
            def write(self, prompt, n):
                time.sleep(0.5)
                return inner.write(prompt, n)
        return Slow()

    state.writer_factory = slow
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    codes = []

    def go():
        from verdict.api.main import create_app

        c = TestClient(create_app(state, frontend_dist=None))
        c.headers["Authorization"] = token
        r = c.post("/api/ask", json={"question": "How many?", "database_id": "tiny", "model": "fixed"})
        codes.append(r.status_code)

    threads = [threading.Thread(target=go) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 402, 402]
    assert client.get("/api/me").json()["credits"]["balance"] == 0


# -- the provider panel -------------------------------------------------------------

def test_admin_adds_and_takes_back_credits(env):
    client, _, state = env
    admin = admin_client(state)
    uid = my_id(client)

    rows = {r["id"]: r for r in admin.get("/api/admin/users").json()}
    assert rows[uid]["balance"] == 1000 and rows[uid]["role"] == "analyst"
    assert set(rows[uid]) == {"id", "name", "email", "role", "active", "created_at", "balance",
                              "used_total", "asks_count", "last_active_at"}
    assert rows[uid]["last_active_at"] is None

    r = admin.post(f"/api/admin/users/{uid}/credits", json={"amount": 5, "note": "bonus"})
    assert r.status_code == 200 and r.json()["balance"] == 1005
    r = admin.post(f"/api/admin/users/{uid}/credits", json={"amount": -1005, "note": "take back"})
    assert r.status_code == 200 and r.json()["balance"] == 0
    assert admin.post(f"/api/admin/users/{uid}/credits", json={"amount": -1}).status_code == 400
    assert admin.post(f"/api/admin/users/{uid}/credits", json={"amount": 0}).status_code == 400
    assert admin.post("/api/admin/users/u_nobody/credits", json={"amount": 1}).status_code == 404

    usage = admin.get(f"/api/admin/users/{uid}/usage").json()
    assert [u["kind"] for u in usage][:2] == ["remove", "grant"]
    assert usage[0]["note"] == "take back"
    # The balance is always the sum of the ledger.
    assert sum(u["amount"] for u in usage) == 0


def test_analyst_cannot_use_admin_routes(env):
    client, _, _ = env
    assert client.get("/api/admin/users").status_code == 403
    assert client.post(f"/api/admin/users/{my_id(client)}/credits", json={"amount": 100}).status_code == 403


def test_turned_off_account(env):
    client, _, state = env
    admin = admin_client(state)
    uid = my_id(client)
    r = admin.post(f"/api/admin/users/{uid}/active", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    # Its logins ended, and it cannot log in again.
    assert client.get("/api/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "ana@test.local", "password": "password-123"})
    assert r.status_code == 403
    # The provider cannot turn off their own account.
    admin_id = admin.get("/api/me").json()["user"]["id"]
    assert admin.post(f"/api/admin/users/{admin_id}/active", json={"active": False}).status_code == 400
    assert admin.post(f"/api/admin/users/{uid}/active", json={"active": True}).json()["active"] is True


def test_first_admin_comes_from_config(env):
    _, _, state = env
    admin = admin_client(state)
    assert admin.get("/api/me").json()["user"]["role"] == "admin"
    # Starting the server again does not make a second admin.
    admin_client(state)
    assert sum(1 for r in admin.get("/api/admin/users").json() if r["role"] == "admin") == 1


# -- whose data is whose ----------------------------------------------------------------

def test_one_user_cannot_read_another_users_ask(env):
    client, w, state = env
    w.replies = [block("SELECT 1"), block("SELECT 2")]
    a = ask(client, "anything?")       # reject: also a review item
    rid = a["review_id"]

    other = TestClient(client.app)
    login_as(other, signup(other, "eve@test.local", name="Eve"))
    assert other.get(f"/api/asks/{a['ask_id']}").status_code == 404
    assert other.get(f"/api/asks/{a['ask_id']}/events").status_code == 404
    assert other.post(f"/api/asks/{a['ask_id']}/flag", json={"note": "x"}).status_code == 404
    assert other.get(f"/api/review/{rid}").status_code == 404
    assert other.post(f"/api/review/{rid}/resolve", json={"action": "reject"}).status_code == 404
    assert other.get("/api/asks").json() == []
    assert other.get("/api/review").json()["items"] == []

    admin = admin_client(state)
    assert admin.get(f"/api/asks/{a['ask_id']}").status_code == 200
    assert any(i["review_id"] == rid for i in admin.get("/api/review").json()["items"])
    row = next(r for r in admin.get("/api/admin/users").json() if r["email"] == "ana@test.local")
    assert row["asks_count"] == 1 and row["last_active_at"] is not None


# -- saved answers and the event log ------------------------------------------------------

def test_saved_answers(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    a = ask(client, "How many students?")
    s = client.post("/api/saved", json={"ask_id": a["ask_id"], "name": "Student count"}).json()
    assert s["name"] == "Student count" and s["level"] == "trusted" and s["last_value"] == "3"
    assert s["changed"] is False and s["sql"] == "SELECT COUNT(*) FROM students"
    assert client.get("/api/saved").json() == [s]

    w.replies = [block("SELECT COUNT(*) + 1 FROM students")] * 8
    r = client.post(f"/api/saved/{s['id']}/rerun").json()
    assert r["last_value"] == "4" and r["changed"] is True and r["ask_id"] != a["ask_id"]
    assert client.get("/api/me").json()["credits"]["balance"] == 998   # two asks

    other = TestClient(client.app)
    login_as(other, signup(other, "eve@test.local", name="Eve"))
    assert other.get("/api/saved").json() == []
    assert other.delete(f"/api/saved/{s['id']}").status_code == 404
    assert other.post("/api/saved", json={"ask_id": a["ask_id"], "name": "x"}).status_code == 404

    assert client.delete(f"/api/saved/{s['id']}").json() == {"ok": True}
    assert client.get("/api/saved").json() == []


def test_ask_events(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    a = ask(client, "How many students?")
    client.post(f"/api/asks/{a['ask_id']}/flag", json={"note": "looks wrong"})
    ev = client.get(f"/api/asks/{a['ask_id']}/events").json()
    assert [(e["actor"], e["action"]) for e in ev] == [("verdict", "asked"), ("analyst", "flagged")]
    assert ev[1]["detail"] == "looks wrong" and set(ev[0]) == {"actor", "action", "detail", "created_at"}


# -- old app.db files -------------------------------------------------------------------

def test_old_app_db_gets_new_columns(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE asks (id TEXT PRIMARY KEY, database_id TEXT NOT NULL, question TEXT NOT NULL,"
        " model TEXT NOT NULL, level TEXT NOT NULL, answer_text TEXT, response TEXT NOT NULL,"
        " latency_ms INTEGER NOT NULL, created_at TEXT NOT NULL, flagged INTEGER NOT NULL DEFAULT 0,"
        " flag_note TEXT);"
        "INSERT INTO asks (id, database_id, question, model, level, response, latency_ms, created_at)"
        " VALUES ('a_old', 'tiny', 'q', 'm', 'trusted', '{}', 1, '2026-11-01');"
    )
    con.commit()
    con.close()
    Store(p)
    cols = {r[1] for r in sqlite3.connect(p).execute("PRAGMA table_info(asks)")}
    assert "user_id" in cols
    assert Store(p).list_asks() and Store(p).list_asks(user_id="u_x") == []


def test_login_is_rate_limited(env):
    client, _, state = env
    from verdict.api.main import create_app

    state.auth_rate_per_minute = 3
    c = TestClient(create_app(state, frontend_dist=None))
    codes = [c.post("/api/auth/login", json={"email": "ana@test.local", "password": "bad-guess"}).status_code
             for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
