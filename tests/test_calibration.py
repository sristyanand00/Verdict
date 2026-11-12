from verdict.eval.calibration import (
    agreement_table, cannot_answer_sweep, choose_thresholds, split, summarize,
)
from verdict.eval.metrics import wilson

T = {"green": 0.75, "yellow": 0.5, "cannot_answer": 0.5}


def rec(i, top, right, n=8, cannot=0, empty=False, single=None, answerable=True, difficulty="simple"):
    single = right if single is None else single
    return {
        "key": f"{'A' if answerable else 'U'}:{i}", "question_id": i, "db_id": "d",
        "difficulty": difficulty, "answerable": answerable, "n": n, "n_cannot": cannot,
        "n_failed": 0, "group_sizes": [top] if top else [], "top_empty": empty,
        "group_correct": [right] if top else [], "attempt_correct": [single] + [None] * (n - 1),
        "sqls": ["cannot_answer" if cannot == n else "SELECT 1"] + ["x"] * (n - 1),
        "gold_status": "ok" if answerable else "none",
    }


def test_wilson_interval():
    lo, hi = wilson(85, 100)
    assert 0.76 < lo < 0.78 and 0.90 < hi < 0.92
    assert wilson(0, 0) == (0.0, 0.0)


def test_agreement_table_counts_and_accuracy():
    recs = [rec(i, 8, True) for i in range(9)] + [rec(9, 8, False)] + [rec(10, 4, False)]
    rows = {r["agree"]: r for r in agreement_table(recs)}
    assert rows[8]["n"] == 10 and rows[8]["rate"] == 0.9
    assert rows[4]["n"] == 1 and rows[4]["rate"] == 0.0


def make_mixed():
    # >=7 agree: 40 questions, all right. 6 agree: 3/20 right. 4 agree: 10/20 right.
    return ([rec(i, 8, True) for i in range(20)] + [rec(100 + i, 7, True) for i in range(20)]
            + [rec(200 + i, 6, i < 3) for i in range(20)] + [rec(300 + i, 4, i < 10) for i in range(20)])


def test_thresholds_pick_lowest_level_meeting_target():
    fit = choose_thresholds(make_mixed(), green_target=0.85, yellow_target=0.6, min_support=10)
    assert fit["green"] == 7 / 8          # >=7 is 100% right; >=6 drops to 72%
    assert fit["yellow"] == 1 / 8         # everything together is 66% right
    assert fit["fit"]["green_target_met"]


def test_unreachable_green_target_means_never_green():
    recs = [rec(i, 8, i % 2 == 0) for i in range(20)]
    fit = choose_thresholds(recs, green_target=0.9, min_support=10)
    assert fit["green"] > 1 and not fit["fit"]["green_target_met"]
    # and "never" really means never, even at 8/8
    s = summarize(recs, [], {**T, "green": fit["green"], "yellow": fit["yellow"]})
    assert s["answerable"]["levels"]["green"] == 0


def test_empty_answers_are_not_counted_for_green():
    recs = [rec(i, 8, True) for i in range(10)] + [rec(50 + i, 8, False, empty=True) for i in range(10)]
    # Without the empties, the 10 remaining answers are all right.
    fit = choose_thresholds(recs, green_target=0.9, yellow_target=0.9, min_support=10)
    assert fit["green"] == 1 / 8
    # Yellow counts the empties (10/20 right), so the 90% target is not met.
    assert fit["fit"]["yellow_k"] is None


def test_summary_counts_confident_wrong_answers():
    recs = make_mixed()
    s = summarize(recs, [], {**T, "green": 7 / 8})["answerable"]
    assert s["questions"] == 80
    assert s["green"]["coverage"]["k"] == 40 and s["green"]["accuracy"]["rate"] == 1.0
    assert s["confident_wrong"]["single_app"] == 80 - 53
    assert s["confident_wrong"]["verdict_green"] == 0


def test_unanswerable_summary_and_sweep():
    una = [rec(i, 0, None, cannot=8, answerable=False) for i in range(6)] +           [rec(10 + i, 8, None, answerable=False) for i in range(4)]
    s = summarize([rec(0, 8, True)], una, T)["unanswerable"]
    assert s["refused"]["k"] == 6 and s["green"]["k"] == 4
    sweep = cannot_answer_sweep([rec(0, 8, True)], una, T)
    assert all(row["unanswerable_caught"]["k"] == 6 for row in sweep)


def test_split_is_deterministic_and_disjoint():
    recs = [rec(i, 8, True) for i in range(40)]
    a1, b1 = split(recs, 0)
    a2, b2 = split(recs, 0)
    assert [r["key"] for r in a1] == [r["key"] for r in a2]
    assert len(a1) == 20 and not {r["key"] for r in a1} & {r["key"] for r in b1}
