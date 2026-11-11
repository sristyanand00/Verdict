import pytest

from verdict.audit.taxonomy import AnnotationError as E
from verdict.audit.taxonomy import categorize_error, summarize_errors


@pytest.mark.parametrize(
    "status,msg,expected",
    [
        ("ok", None, E.OK),
        ("timeout", None, E.TIMEOUT),
        ("blocked", "not authorized", E.BLOCKED_QUERY),
        ("crashed", "boom", E.CRASHED),
        ("error", 'OperationalError: near "FORM": syntax error', E.SYNTAX_ERROR),
        ("error", "OperationalError: no such table: schools", E.MISSING_TABLE),
        ("error", "OperationalError: no such column: T1.nearby", E.MISSING_COLUMN),
        ("error", "OperationalError: unable to open database file", E.MISSING_DATABASE),
        ("error", "OperationalError: ambiguous column name: id", E.OTHER_ERROR),
    ],
)
def test_categorize(status, msg, expected):
    assert categorize_error(status, msg) is expected


def test_summarize():
    rows = [
        {"status": "ok", "error_msg": None},
        {"status": "ok", "error_msg": None},
        {"status": "error", "error_msg": "no such table: x"},
    ]
    assert summarize_errors(rows) == {"missing_table": 1, "ok": 2}
