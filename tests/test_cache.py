"""Repeated questions come from the cache until something that changes the answer changes."""

import pytest

from tests.test_accounts import admin_client
from tests.test_api import ask, block, env  # noqa: F401  (env is a fixture)


@pytest.fixture
def cenv(env):
    client, w, state = env
    state.cache_enabled = True
    return client, w, state


def test_repeat_is_a_cache_hit_and_still_saved_and_charged(cenv):
    client, w, _ = cenv
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    a = ask(client, "How many students?")
    assert a["cache_hit"] is False and a["cached_at"] is None

    prompts = len(w.prompts)
    w.replies = [block("SELECT 99")] * 8          # would give another answer if it ran
    b = ask(client, "  how many STUDENTS?  ")    # case and spacing ignored
    assert b["cache_hit"] is True and b["cached_at"] is not None
    assert b["answer_text"] == "3" and b["ask_id"] != a["ask_id"]
    assert b["question"] == "  how many STUDENTS?  "
    assert len(w.prompts) == prompts             # the model was not called

    assert client.get(f"/api/asks/{b['ask_id']}").status_code == 200
    assert client.get("/api/me").json()["credits"]["used_total"] == 2


def test_knowledge_change_skips_the_cache(cenv):
    client, w, _ = cenv
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    ask(client, "How many students?")
    client.post("/api/knowledge/meanings", json={"database_id": "tiny", "term": "x", "definition": "y"})
    w.replies = [block("SELECT 99")] * 8
    r = ask(client, "How many students?")
    assert r["cache_hit"] is False and r["answer_text"] == "99"


def test_review_answer_from_cache_goes_to_the_queue_again(cenv):
    client, w, _ = cenv
    w.replies = [block("SELECT 1")] * 5 + [block("SELECT 2")] * 3
    a = ask(client, "anything?")
    b = ask(client, "anything?")
    assert b["cache_hit"] is True and b["level"] == a["level"] == "review"
    assert b["review_id"] and b["review_id"] != a["review_id"]


def test_saved_rerun_is_always_fresh(cenv):
    client, w, _ = cenv
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    a = ask(client, "How many students?")
    s = client.post("/api/saved", json={"ask_id": a["ask_id"], "name": "n"}).json()
    w.replies = [block("SELECT COUNT(*) + 1 FROM students")] * 8
    r = client.post(f"/api/saved/{s['id']}/rerun").json()
    assert r["last_value"] == "4" and r["changed"] is True


def test_provider_asks_are_free_and_can_clear_the_cache(cenv):
    client, w, state = cenv
    admin = admin_client(state)
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    ask(admin, "How many students?")
    assert admin.get("/api/me").json()["credits"] == {"balance": 0, "used_total": 0, "used_this_month": 0}
    assert [c["question"] for c in admin.get("/api/admin/cache").json()] == ["How many students?"]
    assert client.get("/api/admin/cache").status_code == 403
    assert admin.delete("/api/admin/cache").json() == {"ok": True, "removed": 1}
    assert admin.get("/api/admin/cache").json() == []


def test_model_down_after_a_knowledge_change_serves_the_earlier_answer(cenv):
    client, w, _ = cenv
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    ask(client, "How many students?")
    client.post("/api/knowledge/meanings", json={"database_id": "tiny", "term": "x", "definition": "y"})
    w.down = True
    r = ask(client, "How many students?")
    assert r["cache_hit"] is True and r["cache_stale"] is True and r["answer_text"] == "3"
    # a question that was never answered still fails
    assert client.post("/api/ask", json={"question": "Something new?"}).status_code == 503
    # with the model back, the next ask runs fresh on the new knowledge
    w.down = False
    w.replies = [block("SELECT 99")] * 8
    r = ask(client, "How many students?")
    assert r["cache_hit"] is False and r["answer_text"] == "99"
