from tests.fixtures import make_tiny_db
from verdict.engine.generate import Attempt
from verdict.engine.group import run_and_group


def sql(q):
    return Attempt("sql", sql=q)


def test_different_sql_same_answer_is_one_group(tmp_path):
    db = make_tiny_db(tmp_path)
    g = run_and_group([
        sql("SELECT COUNT(*) FROM students"),
        sql("SELECT COUNT(id) FROM students"),
        sql("SELECT 3.0"),
        sql("SELECT COUNT(*) FROM marks"),
    ], db)
    assert [grp.size for grp in g.groups] == [3, 1]
    assert g.top.members == [0, 1, 2]


def test_row_order_ignored_unless_both_ask_for_it(tmp_path):
    db = make_tiny_db(tmp_path)
    g = run_and_group([
        sql("SELECT name FROM students ORDER BY name"),
        sql("SELECT name FROM students"),
        sql("SELECT name FROM students ORDER BY name DESC"),
    ], db)
    # 0 and 1 match (one is unordered); 2 orders differently from 0.
    assert [grp.members for grp in g.groups] == [[0, 1], [2]]


def test_failures_and_refusals_are_counted_not_grouped(tmp_path):
    db = make_tiny_db(tmp_path)
    g = run_and_group([
        sql("SELECT * FROM no_such_table"),
        sql("DELETE FROM students"),
        Attempt("cannot_answer"),
        Attempt("empty"),
        sql("SELECT 1"),
    ], db)
    assert g.n_failed == 3
    assert g.n_cannot_answer == 1
    assert len(g.groups) == 1
    assert g.results[1].status == "blocked"


def test_empty_answer_detected(tmp_path):
    db = make_tiny_db(tmp_path)
    g = run_and_group([sql("SELECT SUM(score) FROM marks WHERE subject = 'dbms'")], db)
    assert g.top.is_empty_answer
