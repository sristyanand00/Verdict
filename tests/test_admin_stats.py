"""The usage log and GET /api/admin/stats."""

from verdict.api.routes.admin_stats import _p95, summarize
from verdict.engine.llm import OpenAICompatWriter

from tests.test_api import as_admin, ask, block, env  # noqa: F401  (env is a fixture)


def test_stats_are_for_the_provider_only(env):
    client, _, _ = env
    assert client.get("/api/admin/stats").status_code == 403


def test_every_run_is_logged_answered_cached_and_failed(env):
    client, w, state = env
    state.cache_enabled = True
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    a = ask(client, "How many students?")
    assert a["usage"]["model_ms"] >= 0 and a["cache_hit"] is False
    b = ask(client, "How many students?")
    assert b["cache_hit"] is True and b["usage"] == {"model_ms": 0, "prompt_tokens": 0, "completion_tokens": 0}
    w.down = True
    r = client.post("/api/ask", json={"question": "Another one?", "database_id": "tiny", "model": "fixed"})
    assert r.status_code == 503

    st = as_admin(client).get("/api/admin/stats").json()
    t = st["totals"]["all_time"]
    assert t["runs"] == 3 and t["asks"] == 3 and t["answered"] == 2 and t["from_cache"] == 1
    assert t["failed"]["model_down"] == 1 and t["levels"]["trusted"] == 2
    assert t["avg_ms"] is not None and t["active_users"] == 1
    assert st["totals"]["today"]["runs"] == 3
    assert st["per_day"][-1]["runs"] == 3 and len(st["per_day"]) == 14
    assert st["by_model"][0]["model"] == "fixed" and st["by_model"][0]["failed"] == 1
    assert st["recent_failures"][0]["outcome"] == "model_down"
    assert st["users"]["total"] == 2 and st["review"]["open"] == 0
    m = st["machine"]
    assert m["cpu_count"] and m["app_db_mb"] is not None and isinstance(m["gpus"], list)


def test_summary_numbers():
    rows = [
        {"kind": "ask", "outcome": "ok", "cache_hit": 0, "level": "trusted", "total_ms": t,
         "model_ms": t // 2, "prompt_tokens": 100, "completion_tokens": 10, "user_id": "u1"}
        for t in (1000, 2000, 3000, 4000)
    ] + [{"kind": "arena", "outcome": "timeout", "cache_hit": 0, "level": None, "total_ms": 9000,
          "model_ms": None, "prompt_tokens": None, "completion_tokens": None, "user_id": "u2"}]
    s = summarize(rows)
    assert s["avg_ms"] == 2500 and s["p95_ms"] == 4000 and s["avg_model_ms"] == 1250
    assert s["prompt_tokens"] == 400 and s["completion_tokens"] == 40
    assert s["failed"]["timeout"] == 1 and s["arena_runs"] == 1 and s["active_users"] == 2
    assert _p95([]) is None


def test_openai_writer_adds_up_reported_tokens(monkeypatch):
    w = OpenAICompatWriter("http://x/v1", "m")

    def fake_one(prompt):
        w._add_usage(30, 5)
        return "ok", None

    monkeypatch.setattr(w, "_one", fake_one)
    assert w.write("p", 4) == ["ok"] * 4
    assert w.last_usage == {"prompt_tokens": 120, "completion_tokens": 20}
