"""The API end to end, on the tiny fixture database with fixed model replies."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import make_tiny_db
from verdict.api.main import create_app
from verdict.api.state import AppState, Database, ModelEntry
from verdict.engine.llm import FixedWriter, LLMError
from verdict.store.db import Store

T = {"green": 0.75, "yellow": 0.5, "cannot_answer": 0.5}


def block(q):
    return f"```sql\n{q}\n```"


class Writers:
    """Lets each test set the replies the next ask gets, and see the prompts."""

    def __init__(self):
        self.replies = [block("SELECT 1")]
        self.prompts = []
        self.down = False

    def __call__(self, model):
        if self.down:
            class Down:
                def write(self, prompt, n):
                    raise LLMError("connection refused")
            return Down()
        w = FixedWriter(self.replies)
        outer = self

        class Recording:
            def write(self, prompt, n):
                outer.prompts.append(prompt)
                return w.write(prompt, n)
        return Recording()


@pytest.fixture
def env(tmp_path):
    db = make_tiny_db(tmp_path)
    writers = Writers()
    state = AppState(
        store=Store(tmp_path / "app.db"),
        models=[ModelEntry("fixed", "Fixed replies", "fixed", True)],
        preloaded=[
            Database("tiny", "Tiny school", db, "preloaded"),
            Database("gone", "Missing", tmp_path / "nope.sqlite", "preloaded"),
        ],
        results_dir=tmp_path / "results",
        thresholds=T,
        writer_factory=writers,
        reachable=lambda m: True,
        signup_credits=1000,
        admin_email="admin@test.local",
        admin_password="admin-password-1",
        auth_rate_per_minute=0,
        cache_enabled=False,
        ask_rate_per_minute=0,
    )
    client = TestClient(create_app(state, frontend_dist=None))
    login_as(client, signup(client, "ana@test.local"))
    return client, writers, state


def signup(client, email, password="password-123", name="Ana"):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def login_as(client, token):
    client.headers["Authorization"] = f"Bearer {token}"


def as_admin(client):
    """A second client on the same app, logged in as the provider."""
    a = TestClient(client.app)
    r = a.post("/api/auth/login", json={"email": "admin@test.local", "password": "admin-password-1"})
    assert r.status_code == 200, r.text
    login_as(a, r.json()["token"])
    return a


def ask(client, q, **kw):
    r = client.post("/api/ask", json={"question": q, "database_id": "tiny", "model": "fixed", **kw})
    assert r.status_code == 200, r.text
    return r.json()


# -- basics ------------------------------------------------------------------

def test_health(env):
    client, _, _ = env
    h = client.get("/api/health").json()
    assert h["ok"] and h["databases"] == {"tiny": True, "gone": False}
    assert h["models"] == {"fixed": True} and h["results_ready"] is False


def test_databases_and_schema(env):
    client, _, _ = env
    dbs = {d["id"]: d for d in client.get("/api/databases").json()}
    assert dbs["tiny"]["tables_count"] == 2 and dbs["gone"]["available"] is False
    sch = client.get("/api/databases/tiny/schema").json()
    students = next(t for t in sch["tables"] if t["name"] == "students")
    assert students["row_count"] == 3
    assert {"name": "name", "type": "TEXT"} in students["columns"]
    assert client.get("/api/databases/gone/schema").status_code == 409
    assert client.get("/api/databases/nope/schema").status_code == 404


# -- asking --------------------------------------------------------------------

def test_trusted_answer(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 7 + [block("SELECT 99")]
    r = ask(client, "How many students?")
    assert r["level"] == "trusted" and r["agreement_level"] == "green"
    assert r["answer_text"] == "3" and r["rows"] == [[3]] and r["columns"] == ["COUNT(*)"]
    assert r["sql"] == "SELECT COUNT(*) FROM students"
    assert r["review_id"] is None
    assert [g["size"] for g in r["groups"]] == [7, 1]
    assert len(r["attempts"]) == 8 and r["attempts"][7]["group"] == 1
    assert {c["key"] for c in r["checks"]} >= {"safe", "ran", "agreement", "second_model"}
    assert r["tested_trust"] is None

    listed = client.get("/api/asks").json()
    assert listed[0]["ask_id"] == r["ask_id"] and listed[0]["level"] == "trusted"
    again = client.get(f"/api/asks/{r['ask_id']}").json()
    assert again["sql"] == r["sql"] and again["flagged"] is False


def test_settings_pick_database_and_model(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")]
    as_admin(client).put("/api/settings", json={"database_id": "tiny", "model": "fixed"})
    r = client.post("/api/ask", json={"question": "How many students?"})
    assert r.status_code == 200 and r.json()["database_id"] == "tiny"


def test_bad_requests(env):
    client, _, _ = env
    assert client.post("/api/ask", json={"question": "q", "database_id": "nope", "model": "fixed"}).status_code == 404
    assert client.post("/api/ask", json={"question": "q", "database_id": "tiny", "model": "nope"}).status_code == 400
    assert client.post("/api/ask", json={"question": "", "database_id": "tiny"}).status_code == 422
    assert client.get("/api/asks/a_missing").status_code == 404


def test_model_down_is_503(env):
    client, w, _ = env
    w.down = True
    r = client.post("/api/ask", json={"question": "q", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]


def test_not_in_data_is_reject(env):
    client, w, _ = env
    w.replies = ["CANNOT_ANSWER: there is no attendance table"]
    r = ask(client, "What is attendance?")
    assert r["level"] == "reject" and r["reasons"][0]["code"] == "not_in_data"
    assert r["missing"] == "there is no attendance table"
    assert sorted(r["tables_available"]) == ["marks", "students"]
    assert r["answer_text"] is None and r["sql"] is None
    assert r["review_id"] is not None


def test_two_meanings_then_choose(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM marks")] * 4 + \
                [block("SELECT COUNT(*) FROM marks WHERE score IS NOT NULL")] * 4
    r = ask(client, "How many marks?")
    assert r["level"] == "review" and r["reasons"][0]["code"] == "two_meanings"
    assert r["answer_text"] is None
    labels = [o["label"] for o in r["options"]]
    assert labels[1].startswith("Only where") and [o["answer_text"] for o in r["options"]] == ["4", "3"]

    done = client.post(f"/api/asks/{r['ask_id']}/choose", json={"option": 1}).json()
    assert done["status"] == "approved" and done["final_rows"] == [[3]]
    kn = client.get("/api/knowledge", params={"database_id": "tiny"}).json()
    assert kn["examples"][0]["question"] == "How many marks?"
    assert client.post(f"/api/asks/{r['ask_id']}/choose", json={"option": 5}).status_code == 400


# -- the learning loop (plan flow 4) ------------------------------------------------

def test_review_fix_then_similar_question_uses_it(env):
    client, w, _ = env
    # 1. Five of eight agree: review, goes to the queue.
    w.replies = [block("SELECT AVG(score) FROM marks")] * 5 + [block("SELECT 1")] * 2 + [block("SELECT 2")]
    r = ask(client, "What is the average DBMS score?")
    assert r["level"] == "review" and r["reasons"][0]["code"] == "agreement"
    queue = client.get("/api/review").json()
    assert queue["items"][0]["review_id"] == r["review_id"]
    assert queue["open_counts"] == {"review": 1} and queue["today"]["asked"] == 1

    # 2. The analyst opens it, tries SQL, fixes it, and saves a meaning.
    item = client.get(f"/api/review/{r['review_id']}").json()
    assert item["ask"]["question"] == "What is the average DBMS score?"
    fix_sql = "SELECT AVG(score) FROM marks WHERE subject = 'DBMS'"
    tried = client.post("/api/sql/run", json={"database_id": "tiny", "sql": fix_sql}).json()
    assert tried["status"] == "ok" and tried["rows"] == [[82.5]]
    done = client.post(f"/api/review/{r['review_id']}/resolve", json={
        "action": "fix", "sql": fix_sql, "note": "filter on subject",
        "save_meaning": {"term": "DBMS score", "definition": "score where subject = 'DBMS'"},
        "save_known_number": {"name": "Average DBMS score"},
    }).json()
    assert done["status"] == "fixed" and done["final_rows"] == [[82.5]]
    assert client.get("/api/review").json()["items"] == []

    # 3. A similar question: the approved example and meaning go into the prompt.
    w.replies = [block(fix_sql)] * 8
    r2 = ask(client, "Average DBMS score for all students?")
    assert "Q: What is the average DBMS score?" in w.prompts[-1]
    assert "DBMS score = score where subject = 'DBMS'" in w.prompts[-1]
    assert r2["level"] == "trusted"
    assert any("DBMS score" in k for k in r2["knowledge_used"])

    # 4. The same question again with a different answer is a conflict: review.
    w.replies = [block("SELECT AVG(score) FROM marks")] * 8
    r3 = ask(client, "What is the average DBMS score?")
    assert r3["level"] == "review" and r3["reasons"][0]["code"] == "conflict"
    known = next(c for c in r3["checks"] if c["key"] == "known_numbers")
    assert known["status"] == "fail"


def test_resolve_rules(env):
    client, w, _ = env
    w.replies = [block("SELECT AVG(score) FROM marks")] * 5 + [block("SELECT 1")] * 2 + [block("SELECT 2")]
    rid = ask(client, "avg score?")["review_id"]
    url = f"/api/review/{rid}/resolve"
    assert client.post(url, json={"action": "fix"}).status_code == 400
    bad = client.post(url, json={"action": "fix", "sql": "SELECT nope FROM nowhere"})
    assert bad.status_code == 400 and bad.json()["detail"]["result"]["status"] == "error"
    assert client.post(url, json={"action": "approve"}).json()["status"] == "approved"
    assert client.post(url, json={"action": "approve"}).status_code == 409
    assert client.post("/api/review/r_missing/resolve", json={"action": "reject"}).status_code == 404


def test_reject_item(env):
    client, w, _ = env
    w.replies = ["CANNOT_ANSWER"]
    rid = ask(client, "attendance?")["review_id"]
    done = client.post(f"/api/review/{rid}/resolve", json={"action": "reject", "note": "no data"}).json()
    assert done["status"] == "rejected" and done["note"] == "no data"
    assert client.get("/api/knowledge", params={"database_id": "tiny"}).json()["examples"] == []


def test_flag_trusted_answer(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")]
    r = ask(client, "How many students?")
    f = client.post(f"/api/asks/{r['ask_id']}/flag", json={"note": "should exclude year 3"}).json()
    assert f["ok"]
    item = client.get(f"/api/review/{f['review_id']}").json()
    assert item["source"] == "flagged" and item["ask"]["flagged"] is True
    assert item["ask"]["flag_note"] == "should exclude year 3"
    # Flagging twice does not make a second item.
    again = client.post(f"/api/asks/{r['ask_id']}/flag", json={"note": "x"}).json()
    assert again["review_id"] == f["review_id"]


# -- SQL, knowledge, settings, results ------------------------------------------------

def test_sql_run_is_read_only(env):
    client, _, _ = env
    r = client.post("/api/sql/run", json={"database_id": "tiny", "sql": "DELETE FROM students"}).json()
    assert r["status"] == "blocked"
    r = client.post("/api/sql/run", json={"database_id": "tiny", "sql": "SELECT COUNT(*) FROM students"}).json()
    assert r["rows"] == [[3]]


def test_meanings_and_known_numbers(env):
    client, w, _ = env
    m = client.post("/api/knowledge/meanings", json={
        "database_id": "tiny", "term": "top student", "definition": "highest average score"}).json()
    assert client.get("/api/knowledge", params={"database_id": "tiny"}).json()["meanings"][0]["id"] == m["id"]
    # Knowledge is shared, so only the provider deletes it.
    assert client.delete(f"/api/knowledge/meanings/{m['id']}").status_code == 403
    admin = as_admin(client)
    assert admin.delete(f"/api/knowledge/meanings/{m['id']}").json() == {"ok": True}
    assert admin.delete(f"/api/knowledge/meanings/{m['id']}").status_code == 404
    assert admin.delete("/api/knowledge/bogus/x").status_code == 400

    w.replies = [block("SELECT COUNT(*) FROM students")] * 5 + [block("SELECT 1")] * 2 + [block("SELECT 2")]
    rid = ask(client, "students?")["review_id"]
    client.post(f"/api/review/{rid}/resolve", json={
        "action": "approve", "save_known_number": {"name": "Students"}})
    k = client.get("/api/knowledge", params={"database_id": "tiny"}).json()["known_numbers"][0]
    check = client.post(f"/api/knowledge/known/{k['id']}/recheck").json()
    assert check["ok"] and not check["changed"] and check["value_now"] == [[3]]


def test_settings(env):
    client, _, _ = env
    s = client.get("/api/settings").json()
    assert s["database_id"] == "tiny" and s["model"] == "fixed" and s["second_model"] is False
    assert client.put("/api/settings", json={"second_model": True}).status_code == 403
    admin = as_admin(client)
    s = admin.put("/api/settings", json={"second_model": True}).json()
    assert s["second_model"] is True
    assert admin.put("/api/settings", json={"model": "nope"}).status_code == 404
    models = client.get("/api/models").json()
    assert models == [{"id": "fixed", "label": "Fixed replies", "kind": "own", "provider": "fixed",
                       "private": True, "reachable": True}]


def test_results_and_arena(env):
    client, _, state = env
    assert client.get("/api/results").status_code == 404
    state.results_dir.mkdir()
    (state.results_dir / "results.json").write_text(json.dumps(
        {"tested_trust": {"precision": 0.9, "low": 0.87, "high": 0.93, "on": "BIRD dev, 1,534"}}))
    (state.results_dir / "arena.json").write_text(json.dumps({"q1": {"answers": []}}))
    assert client.get("/api/results").json()["tested_trust"]["precision"] == 0.9
    # the Arena is for the provider only
    assert client.get("/api/arena").status_code == 403
    assert client.get("/api/arena/models").status_code == 403
    admin = as_admin(client)
    assert admin.get("/api/arena").json() == ["q1"]
    assert admin.get("/api/arena/q1").json() == {"answers": []}
    assert admin.get("/api/arena/q2").status_code == 404
    assert ask(client, "q?")["tested_trust"]["on"] == "BIRD dev, 1,534"


def test_upload_csv(env, tmp_path, monkeypatch):
    monkeypatch.setenv("VERDICT_UPLOADS_ROOT", str(tmp_path / "uploads"))
    client, _, _ = env
    r = client.post("/api/databases/upload",
                    files={"file": ("Sales 2024.csv", b"City,Amount\nPune,10\nDelhi,5\n", "text/csv")})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["source"] == "upload" and up["tables_count"] == 1
    ids = [d["id"] for d in client.get("/api/databases").json()]
    assert up["id"] in ids
    sch = client.get(f"/api/databases/{up['id']}/schema").json()
    assert sch["tables"][0]["row_count"] == 2
    bad = client.post("/api/databases/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400


def test_serves_built_frontend(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>verdict</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    state = AppState(store=Store(tmp_path / "app.db"), models=[], preloaded=[],
                     reachable=lambda m: True)
    client = TestClient(create_app(state, frontend_dist=dist))
    assert client.get("/").text == "<html>verdict</html>"
    assert client.get("/review/r_1").text == "<html>verdict</html>"   # frontend route
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/nothing").status_code == 404


def test_arena_scoreboard_never_fills_numbers(env):
    client, _, state = env
    client = as_admin(client)
    assert client.get("/api/arena/models").json() == []
    state.results_dir.mkdir(exist_ok=True)
    (state.results_dir / "results.json").write_text(json.dumps({"arena_models": [
        {"model_id": "qwen-base", "label": "Qwen2.5-Coder-1.5B base", "kind": "own",
         "benchmark": "BIRD dev", "n_questions": 1534, "accuracy": 0.246, "measured_at": "2026-11-20"},
        {"model_id": "qwen-sft", "label": "Qwen SFT v2", "kind": "own"},
    ]}), encoding="utf-8")
    rows = client.get("/api/arena/models").json()
    assert rows[0]["accuracy"] == 0.246 and rows[0]["n_questions"] == 1534
    assert rows[1]["accuracy"] is None and rows[1]["measured_at"] is None
    # "models" is not read as a cached question key.
    assert client.get("/api/arena").json() == []


def test_ask_has_lineage_only_when_an_answer_is_shown(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    lin = ask(client, "How many students?")["lineage"]
    assert lin["tables"] == ["students"] and lin["formula"] == "COUNT(*)"
    w.replies = [block("SELECT 1"), block("SELECT 2"), block("SELECT 3")]
    assert ask(client, "anything?")["lineage"] is None
