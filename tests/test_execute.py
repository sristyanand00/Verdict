from tests.fixtures import make_tiny_db
from verdict.verifier.execute import execute_query
from verdict.verifier.pool import execute_isolated

INFINITE = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) "
    "SELECT count(*) FROM c"
)


def test_simple_select(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_query("SELECT name FROM students WHERE year = 2", db)
    assert r.ok
    assert set(r.rows) == {("Priya",), ("Rahul",)}
    assert r.columns == ("name",)


def test_bad_sql_returns_error_not_exception(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_query("SELECT * FROM no_such_table", db)
    assert r.status == "error"
    assert "no such table" in r.error.lower()


def test_empty_result_is_still_ok(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_query("SELECT name FROM students WHERE year = 99", db)
    assert r.ok  # "no rows" is a valid answer, not a failure
    assert r.rows == ()


def test_join_and_nulls(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_query(
        "SELECT s.name, m.score FROM students s "
        "LEFT JOIN marks m ON m.student_id = s.id WHERE m.subject='OS'",
        db,
    )
    assert r.ok
    assert ("Aisha", None) in r.rows  # the NULL survives as None


def test_runaway_query_times_out_in_process(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_query(INFINITE, db, timeout_s=1.0)
    assert r.status == "timeout"
    assert r.elapsed_ms < 5000  # stopped early rather than finishing


def test_runaway_query_killed_in_child_process(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_isolated(INFINITE, db, timeout_s=1.0)
    assert r.status == "timeout"


def test_isolated_normal_query(tmp_path):
    db = make_tiny_db(tmp_path)
    r = execute_isolated("SELECT COUNT(*) FROM students", db)
    assert r.ok and r.rows == ((3,),)
