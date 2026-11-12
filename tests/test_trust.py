import pytest

from verdict.engine.group import AnswerGroup, Grouping
from verdict.engine.trust import decide, load_thresholds
from verdict.verifier.types import ExecutionResult

T = {"green": 0.75, "yellow": 0.5, "cannot_answer": 0.5}


def grouping(sizes, n=8, cannot=0, rows=((1,),)):
    groups = [AnswerGroup(ExecutionResult("ok", rows=rows), list(range(s)), ["SELECT 1"] * s) for s in sizes]
    return Grouping(n, groups, cannot, n - sum(sizes) - cannot, [None] * n)


@pytest.mark.parametrize("sizes, level", [
    ([8], "green"), ([6, 2], "green"), ([5, 3], "yellow"),
    ([4, 4], "yellow"), ([3, 3, 2], "red"), ([1] * 8, "red"),
])
def test_levels_follow_agreement(sizes, level):
    assert decide(grouping(sizes), T).level == level


def test_score_and_reason():
    d = decide(grouping([7, 1]), T)
    assert d.score == 7 / 8 and "7 of 8" in d.reason and d.answer.size == 7


def test_majority_cannot_answer_is_unanswerable():
    d = decide(grouping([3], cannot=5), T)
    assert d.level == "unanswerable" and d.answer is None


def test_empty_answer_is_never_green():
    assert decide(grouping([8], rows=((None,),)), T).level == "yellow"
    assert decide(grouping([8], rows=()), T).level == "yellow"


def test_nothing_ran_is_red():
    d = decide(grouping([]), T)
    assert d.level == "red" and d.answer is None


def test_thresholds_file_loads_and_is_valid():
    t = load_thresholds()
    assert 0 < t["yellow"] <= t["green"] <= 1
