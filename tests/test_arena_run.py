"""Model Arena: provider only; trained Qwen, base Qwen and outside models side by side."""

import pytest

from tests.test_api import as_admin, block, env  # noqa: F401  (env is a fixture)
from verdict.api.state import ModelEntry, default_models
from verdict.engine.llm import FixedWriter, LLMError


@pytest.fixture
def arena(env):
    client, w, state = env
    state.models = state.models + [
        ModelEntry("base", "Base model", "fixed", True, arena_only=True),
        ModelEntry("cloud", "Cloud model", "fixed", False, own=False),
    ]
    calls = {"cloud": 0}
    own_factory = state.writer_factory
    cloud = {"down": False}

    def factory(m):
        if m.id == "base":
            return FixedWriter([block("SELECT COUNT(*) FROM nope")])
        if m.id != "cloud":
            return own_factory(m)

        class Cloud:
            def write(self, prompt, n):
                calls["cloud"] += 1
                if cloud["down"]:
                    raise LLMError("quota")
                return FixedWriter([block("SELECT COUNT(*) FROM students")]).write(prompt, n)
        return Cloud()

    state.writer_factory = factory
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    return client, as_admin(client), state, calls, cloud


def run(client, models, q="How many students?"):
    return client.post("/api/arena/run", json={"question": q, "database_id": "tiny", "models": models})


def by_model(r):
    return {x["model_id"]: x for x in r.json()["results"]}


def test_analysts_cannot_use_the_arena(arena):
    client, _, _, calls, _ = arena
    assert run(client, ["fixed"]).status_code == 403
    assert calls["cloud"] == 0


def test_three_kinds_side_by_side_and_nothing_saved(arena):
    client, admin, state, calls, _ = arena
    r = run(admin, ["fixed", "base", "cloud"])
    assert r.status_code == 200, r.text
    res = by_model(r)
    assert res["fixed"]["kind"] == "own" and res["fixed"]["level"] == "trusted"
    assert res["fixed"]["answer_text"] == "3" and res["fixed"]["agree"] == 8
    assert res["base"]["kind"] == "base" and res["base"]["level"] == "reject"
    assert res["cloud"]["kind"] == "outside" and res["cloud"]["status"] == "ok"
    assert r.json()["credits_charged"] == 0 and calls["cloud"] == 1
    assert admin.get("/api/asks").json() == []
    assert admin.get("/api/me/usage").json() == []


def test_outside_models_can_be_turned_off(arena):
    _, admin, state, calls, _ = arena
    state.arena_outside_enabled = False
    res = by_model(run(admin, ["fixed", "cloud"]))
    assert res["cloud"]["status"] == "off" and "turned off" in res["cloud"]["error"]
    assert res["fixed"]["status"] == "ok" and calls["cloud"] == 0


def test_repeat_run_comes_from_the_cache(arena):
    _, admin, state, calls, _ = arena
    state.cache_enabled = True
    run(admin, ["fixed", "cloud"])
    r2 = run(admin, ["fixed", "cloud"])
    assert by_model(r2)["cloud"]["cache_hit"] is True and calls["cloud"] == 1


def test_fresh_skips_the_cache_and_leaves_it_alone(arena):
    _, admin, state, calls, _ = arena
    state.cache_enabled = True
    run(admin, ["cloud"])
    r = admin.post("/api/arena/run", json={"question": "How many students?", "database_id": "tiny",
                                           "models": ["cloud"], "fresh": True})
    assert by_model(r)["cloud"]["cache_hit"] is False and calls["cloud"] == 2
    r = admin.post("/api/arena/run", json={"question": "Something new?", "database_id": "tiny",
                                           "models": ["cloud"], "fresh": True})
    assert len(state.store.cache_list()) == 1   # the fresh runs added nothing


def test_a_failing_outside_model_does_not_stop_the_others(arena):
    _, admin, _, _, cloud = arena
    cloud["down"] = True
    res = by_model(run(admin, ["fixed", "cloud"]))
    assert res["cloud"]["status"] == "error" and "not reachable" in res["cloud"]["error"]
    assert "quota" not in res["cloud"]["error"]
    assert res["fixed"]["status"] == "ok"


def test_bad_requests(arena):
    _, admin, _, _, _ = arena
    assert run(admin, ["nope"]).status_code == 400
    assert admin.post("/api/arena/run", json={"question": "x", "database_id": "tiny", "models": []}).status_code == 422


def test_base_model_is_not_for_ask(arena):
    client, _, _, _, _ = arena
    r = client.post("/api/ask", json={"question": "How many students?", "database_id": "tiny", "model": "base"})
    assert r.status_code == 400 and "only for the Model Arena" in r.json()["detail"]


def test_models_list_kinds(arena):
    client, _, _, _, _ = arena
    kinds = {m["id"]: m["kind"] for m in client.get("/api/models").json()}
    assert kinds["fixed"] == "own" and kinds["base"] == "base" and kinds["cloud"] == "outside"


def test_default_models(monkeypatch):
    for k in ("OPENAI_API_KEY", "GROQ_API_KEY", "VERDICT_QWEN_BASE_MODEL", "VERDICT_MODELS_FILE"):
        monkeypatch.delenv(k, raising=False)
    ids = {m.id: m for m in default_models()}
    assert list(ids) == ["qwen", "qwen-base", "gemini"]
    assert ids["qwen-base"].model == "qwen2.5-coder:1.5b" and ids["qwen-base"].role == "base"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VERDICT_QWEN_BASE_MODEL", "off")
    ids = {m.id: m for m in default_models()}
    assert list(ids) == ["qwen", "gemini", "chatgpt"]
    assert ids["chatgpt"].role == "outside" and ids["chatgpt"].api_key_env == "OPENAI_API_KEY"
