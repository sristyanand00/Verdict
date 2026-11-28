"""A single 0 is never Trusted on agreement alone (found on the demo questions:
"How many clients are women?" gave 0 from gender = 'female'; the data says 'F')."""

from tests.test_api import ask, block, env  # noqa: F401  (env is a fixture)


def test_a_zero_count_goes_to_review_even_when_all_attempts_agree(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students WHERE name = 'Nobody'")] * 8
    a = ask(client, "How many students are called Nobody?")
    assert a["answer_text"] == "0"
    assert a["level"] == "review"
    assert [r["code"] for r in a["reasons"]] == ["zero"]
    check = next(c for c in a["checks"] if c["key"] == "not_empty")
    assert check["status"] == "fail" and "0" in check["detail"]


def test_other_answers_are_unchanged(env):
    client, w, _ = env
    w.replies = [block("SELECT COUNT(*) FROM students")] * 8
    assert ask(client, "How many students?")["level"] == "trusted"
    # 0 inside a longer answer is a value like any other
    w.replies = [block("SELECT 0, 1")] * 8
    assert ask(client, "Two numbers?")["level"] == "trusted"
