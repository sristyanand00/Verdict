"""Live Model Arena: own model free, outside models only when allowed, charged only when called."""

import pytest

from tests.test_api import as_admin, block, env  # noqa: F401  (env is a fixture)
from verdict.api.state import ModelEntry
from verdict.engine.llm import FixedWriter, LLMError


@pytest.fixture
def arena(env):
    client, w, state = env
    state.models = state.models + [ModelEntry("cloud", "Cloud model", "fixed", False, own=False)]
    calls = {"cloud": 0}
    own_factory = state.writer_factory
    cloud = {"replies": [block("SELECT COUNT(*) FROM students")], "down": False}

    def factory(m):
        if m.id != "cloud":
            return own_factory(m)

        class Cloud:
            def write(self, prompt, n):
                calls["cloud"] += 1
                if cloud["down"]:
                    raise LLMError("quota")
                return FixedWriter(cloud["replies"]).write(prompt, n)
        return Cloud()

    state.writer_factory = factory
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    return client, state, calls, cloud


def run(client, models, q="How many students?"):
    return client.post("/api/arena/run", json={"question": q, "database_id": "tiny", "models": models})


def by_model(r):
    return {x["model_id"]: x for x in r.json()["results"]}


def test_own_model_runs_free_and_is_not_saved(arena):
    client, _, _, _ = arena
    r = run(client, ["fixed"])
    assert r.status_code == 200, r.text
    res = by_model(r)["fixed"]
    assert res["status"] == "ok" and res["kind"] == "own" and res["level"] == "trusted"
    assert res["answer_text"] == "3" and res["agree"] == 8 and res["n_attempts"] == 8
    assert r.json()["credits_charged"] == 0
    assert client.get("/api/me").json()["credits"]["balance"] == 1000
    assert client.get("/api/asks").json() == []


def test_outside_models_are_off_by_default(arena):
    client, _, calls, _ = arena
    res = by_model(run(client, ["fixed", "cloud"]))
    assert res["cloud"]["status"] == "off" and "turned off" in res["cloud"]["error"]
    assert res["fixed"]["status"] == "ok"
    assert calls["cloud"] == 0
    assert client.get("/api/me").json()["credits"]["balance"] == 1000


def test_outside_model_is_charged_once_then_cached(arena):
    client, state, calls, _ = arena
    state.arena_outside_enabled = True
    state.cache_enabled = True
    r = run(client, ["fixed", "cloud"])
    res = by_model(r)
    assert res["cloud"]["status"] == "ok" and res["cloud"]["kind"] == "outside"
    assert r.json()["credits_charged"] == 1
    row = client.get("/api/me/usage").json()[0]
    assert row["kind"] == "arena" and row["amount"] == -1 and row["note"] == "Arena: Cloud model"
    assert row["question"] == "How many students?"

    r2 = run(client, ["fixed", "cloud"])
    assert by_model(r2)["cloud"]["cache_hit"] is True and r2.json()["credits_charged"] == 0
    assert calls["cloud"] == 1
    assert client.get("/api/me").json()["credits"]["balance"] == 999


def test_a_failing_outside_model_is_not_charged(arena):
    client, state, _, cloud = arena
    state.arena_outside_enabled = True
    cloud["down"] = True
    r = run(client, ["fixed", "cloud"])
    res = by_model(r)
    assert res["cloud"]["status"] == "error" and "not reachable" in res["cloud"]["error"]
    assert "quota" not in res["cloud"]["error"]
    assert res["fixed"]["status"] == "ok"
    assert r.json()["credits_charged"] == 0


def test_not_enough_credits_for_outside_models(arena):
    client, state, calls, _ = arena
    state.arena_outside_enabled = True
    uid = client.get("/api/me").json()["user"]["id"]
    as_admin(client).post(f"/api/admin/users/{uid}/credits", json={"amount": -1000})
    assert run(client, ["fixed", "cloud"]).status_code == 402
    assert calls["cloud"] == 0
    # The own model alone is still free.
    assert run(client, ["fixed"]).status_code == 200


def test_provider_runs_are_free_and_bad_models_rejected(arena):
    client, state, _, _ = arena
    state.arena_outside_enabled = True
    admin = as_admin(client)
    r = run(admin, ["fixed", "cloud"])
    assert r.status_code == 200 and r.json()["credits_charged"] == 0
    assert run(client, ["nope"]).status_code == 400
    assert client.post("/api/arena/run", json={"question": "x", "database_id": "tiny", "models": []}).status_code == 422
