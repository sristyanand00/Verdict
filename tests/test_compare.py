"""Adversarial tests for result comparison."""

import pytest

from verdict.verifier.compare import compare_results, gold_has_order_by
from verdict.verifier.types import ExecutionResult


def res(rows, cols=("a", "b")):
    return ExecutionResult(status="ok", rows=tuple(rows), columns=cols)


# (name, candidate rows, gold rows, gold_sql, expected verdict)
CASES = [
    # formatting
    ("identical",               [(1, "a")],            [(1, "a")],            "SELECT x,y FROM t",            "correct"),
    ("row order no ORDER BY",   [(2, "b"), (1, "a")],  [(1, "a"), (2, "b")],  "SELECT x,y FROM t",            "correct"),
    ("row order WITH ORDER BY", [(2, "b"), (1, "a")],  [(1, "a"), (2, "b")],  "SELECT x,y FROM t ORDER BY x", "wrong"),
    ("int vs float",            [(94.0,)],             [(94,)],               "SELECT s FROM t",              "correct"),
    ("float tolerance",         [(94.00001,)],         [(94.0,)],             "SELECT s FROM t",              "correct"),
    ("real float difference",   [(94.1,)],             [(94.0,)],             "SELECT s FROM t",              "wrong"),
    ("trailing whitespace",     [("Priya ",)],         [("Priya",)],          "SELECT n FROM t",              "correct"),
    ("column order swapped",    [("a", 1)],            [(1, "a")],            "SELECT x,y FROM t",            "correct"),
    ("unicode equal",           [("Aishé",)],     [("Aishé",)],     "SELECT n FROM t",              "correct"),
    ("unicode differs",         [("Aisha",)],          [("Aishé",)],     "SELECT n FROM t",              "wrong"),
    # NULL and empty
    ("NULL vs empty string",    [(None,)],             [("",)],               "SELECT n FROM t",              "wrong"),
    ("NULL vs zero",            [(None,)],             [(0,)],                "SELECT n FROM t",              "wrong"),
    ("NULL equals NULL",        [(None,)],             [(None,)],             "SELECT n FROM t",              "correct"),
    ("both empty",              [],                    [],                    "SELECT n FROM t WHERE 0",      "correct"),
    ("empty vs one row",        [],                    [(1,)],                "SELECT n FROM t",              "wrong"),
    # duplicates
    ("duplicates matter",       [(94,), (71,)],        [(94,), (94,), (71,)], "SELECT s FROM t",              "wrong"),
    ("dup order irrelevant",    [(94,), (71,), (94,)], [(94,), (94,), (71,)], "SELECT s FROM t",              "correct"),
    # shape and types
    ("extra column",            [(1, "a", 9)],         [(1, "a")],            "SELECT x,y FROM t",            "wrong"),
    ("missing column",          [(1,)],                [(1, "a")],            "SELECT x,y FROM t",            "wrong"),
    ("bool vs int",             [(True,)],             [(1,)],                "SELECT b FROM t",              "correct"),
    ("bytes equal",             [(b"\x00\x01",)],      [(b"\x00\x01",)],      "SELECT z FROM t",              "correct"),
    ("numeric string vs num",   [("94",)],             [(94,)],               "SELECT s FROM t",              "wrong"),
    # ORDER BY edge cases
    ("ORDER BY inside string",  [(2,), (1,)],          [(1,), (2,)],
     "SELECT x FROM t WHERE note = 'order by date'",                                                          "correct"),
    ("ORDER BY in subquery only", [(2,), (1,)],        [(1,), (2,)],
     "SELECT x FROM (SELECT x FROM t ORDER BY x)",                                                            "correct"),
    ("UNION with outer ORDER BY", [(2,), (1,)],        [(1,), (2,)],
     "SELECT a FROM t UNION SELECT b FROM u ORDER BY 1",                                                      "wrong"),
    # Regression: sorting values within each row independently judged this correct.
    # A column reordering must be applied to every row.
    ("values swapped between rows", [(1, 2), (2, 1)],  [(1, 2), (1, 2)],      "SELECT a,b FROM t",            "wrong"),
    ("columns swapped, all rows",   [("a", 1), ("b", 2)], [(1, "a"), (2, "b")], "SELECT x,y FROM t",          "correct"),
    ("NaN equals NaN",          [(float("nan"),)],     [(float("nan"),)],     "SELECT x FROM t",              "correct"),
    # Known limitation of rounding: values either side of a boundary differ.
    ("rounding boundary",       [(0.00005,)],          [(0.00004,)],          "SELECT x FROM t",              "wrong"),
    # Known gap, asserted deliberately: a query that returns the expected answer as
    # constants passes. Planned fix: verify against perturbed copies of the database.
    ("hardcoded answer passes (known gap)",
     [("Priya", 94)], [("Priya", 94)], "SELECT name, score FROM t",                                           "correct"),
]


@pytest.mark.parametrize("name,cand,gold,gold_sql,expected", CASES, ids=[c[0] for c in CASES])
def test_comparison(name, cand, gold, gold_sql, expected):
    v = compare_results(res(cand), res(gold), gold_sql)
    assert v.verdict == expected, f"{name}: got {v.verdict} ({v.reason})"


def test_gold_failure_flagged_not_blamed_on_model():
    v = compare_results(
        res([(1,)]), ExecutionResult(status="error", error="no such column: xyz"), "SELECT xyz FROM t"
    )
    assert v.verdict == "invalid" and "GOLD FAILED" in v.reason


def test_gold_timeout_flagged_not_blamed_on_model():
    v = compare_results(res([(1,)]), ExecutionResult(status="timeout"), "SELECT x FROM t")
    assert v.verdict == "invalid" and "GOLD FAILED" in v.reason


def test_candidate_failure_is_invalid_not_wrong():
    v = compare_results(ExecutionResult(status="timeout", error="deadline"), res([(1,)]), "SELECT x FROM t")
    assert v.verdict == "invalid" and "timeout" in v.reason


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("SELECT x FROM t", False),
        ("SELECT x FROM t ORDER BY x", True),
        ("SELECT x FROM t WHERE n = 'order by date'", False),
        ("SELECT x FROM (SELECT x FROM t ORDER BY x)", False),
        ("WITH c AS (SELECT x FROM t ORDER BY x) SELECT x FROM c", False),
        ("WITH c AS (SELECT x FROM t) SELECT x FROM c ORDER BY x", True),
    ],
)
def test_order_by_detection(sql, expected):
    assert gold_has_order_by(sql) is expected
