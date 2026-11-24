"""The product verdict (Trusted / Review / Reject) and the check list."""

from verdict.engine.checks import build_checks
from verdict.engine.group import AnswerGroup, Grouping
from verdict.engine.trust import final_verdict, needed_for_green
from verdict.verifier.types import ExecutionResult

T = {"green": 0.75, "yellow": 0.5, "cannot_answer": 0.5}


def grp(value, size):
    rows = ((None,),) if value is None else ((value,),)
    r = ExecutionResult("ok", rows=rows, columns=("x",))
    return AnswerGroup(r, members=list(range(size)), sqls=["SELECT 1"] * size)


def grouping(*groups, n=8, cannot=0, failed=0):
    results = [g.result for g in groups for _ in range(g.size)]
    results += [ExecutionResult("error", error="no such table")] * failed
    return Grouping(n, list(groups), cannot, failed, results + [None] * (n - len(results)))


def codes(v):
    return [r.code for r in v.reasons]


def test_needed_for_green():
    assert needed_for_green(8, T) == 6
    assert needed_for_green(4, T) == 3


def test_trusted():
    v = final_verdict(grouping(grp(5, 7), grp(6, 1)), T)
    assert v.level == "trusted" and v.agreement_level == "green"
    assert codes(v) == ["agreement", "not_empty"]


def test_not_in_data_is_reject():
    v = final_verdict(grouping(grp(5, 1), cannot=7), T)
    assert v.level == "reject" and codes(v) == ["not_in_data"]


def test_two_meanings_is_review_even_with_low_agreement():
    a, b = grp(1, 3), grp(2, 3)
    v = final_verdict(grouping(a, b, grp(3, 2)), T, split=[a, b])
    assert v.level == "review" and codes(v) == ["two_meanings"]


def test_low_agreement_is_reject():
    v = final_verdict(grouping(grp(1, 3), grp(2, 2), grp(3, 2), grp(4, 1)), T)
    assert v.level == "reject" and codes(v) == ["low_agreement"]


def test_most_failed_is_reject():
    v = final_verdict(grouping(grp(1, 2), failed=6), T)
    assert v.level == "reject" and codes(v) == ["failed"]


def test_nothing_ran_is_reject():
    v = final_verdict(grouping(failed=8), T)
    assert v.level == "reject" and codes(v) == ["failed"]


def test_middling_agreement_is_review():
    v = final_verdict(grouping(grp(1, 5), grp(2, 2), grp(3, 1)), T)
    assert v.level == "review" and codes(v) == ["agreement"]
    assert "trusted needs 6" in v.reasons[0].text


def test_empty_answer_is_never_trusted():
    v = final_verdict(grouping(grp(None, 8)), T)
    assert v.level == "review" and codes(v) == ["empty"]


def test_conflict_lowers_trusted_to_review():
    v = final_verdict(grouping(grp(1, 8)), T, conflict="Differs from the approved answer.")
    assert v.level == "review" and codes(v) == ["conflict"]


def test_second_model_disagreeing_lowers_to_review():
    v = final_verdict(grouping(grp(1, 8)), T, second_model_agrees=False)
    assert v.level == "review" and codes(v) == ["second_model"]


def test_second_model_agreeing_is_listed():
    v = final_verdict(grouping(grp(1, 8)), T, second_model_agrees=True)
    assert v.level == "trusted" and "second_model" in codes(v)


def test_several_review_reasons_are_all_listed():
    v = final_verdict(grouping(grp(1, 5), grp(2, 3)), T, conflict="c", second_model_agrees=False)
    assert codes(v) == ["agreement", "conflict", "second_model"]


# -- checks --------------------------------------------------------------------

def by_key(checks):
    return {c.key: c for c in checks}


def test_checks_for_a_trusted_answer():
    c = by_key(build_checks(grouping(grp(1, 7), grp(2, 1)), T, None, None, 0, ("off", "Off.")))
    assert [k for k in c] == ["safe", "ran", "agreement", "not_empty", "no_split",
                              "known_numbers", "second_model"]
    assert all(c[k].status == "pass" for k in list(c)[:-1])
    assert c["second_model"].status == "off"
    assert c["agreement"].detail.startswith("7 of 8")


def test_checks_report_blocked_attempts():
    g = grouping(grp(1, 6))
    g.results[6] = ExecutionResult("blocked", error="write")
    c = by_key(build_checks(g, T, None, None, 0, ("off", "Off.")))
    assert "1 attempt blocked" in c["safe"].detail
    assert c["ran"].detail == "6 of 7 queries ran without error or timeout."


def test_checks_when_nothing_was_written():
    c = by_key(build_checks(grouping(cannot=8), T, None, None, 0, ("off", "Off.")))
    assert c["ran"].status == "off"
    assert c["not_empty"].status == "off" and c["no_split"].status == "off"


def test_checks_show_split_and_conflict_as_fail():
    a, b = grp(1, 4), grp(2, 4)
    c = by_key(build_checks(grouping(a, b), T, [a, b], None, 0, ("off", "Off.")))
    assert c["no_split"].status == "fail"
    c = by_key(build_checks(grouping(grp(1, 8)), T, None, "Differs.", 1, ("off", "Off.")))
    assert c["known_numbers"].status == "fail" and c["known_numbers"].detail == "Differs."
