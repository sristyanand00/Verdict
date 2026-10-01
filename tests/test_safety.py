import pytest

from tests.fixtures import make_tiny_db
from verdict.verifier.execute import execute_query

HOSTILE = [
    "DROP TABLE students",
    "DELETE FROM students",
    "UPDATE students SET name = 'hacked'",
    "INSERT INTO students VALUES (9, 'evil', 1)",
    "ALTER TABLE students ADD COLUMN x TEXT",
    "CREATE TABLE evil (x INTEGER)",
    "ATTACH DATABASE 'stolen.db' AS s",
    "PRAGMA table_info('students')",
    "WITH t AS (SELECT 1) DELETE FROM students",  # write hidden in a CTE
    "VACUUM",
]


@pytest.mark.parametrize("sql", HOSTILE, ids=[s[:28] for s in HOSTILE])
def test_hostile_sql_is_blocked(tmp_path, sql):
    db = make_tiny_db(tmp_path)
    assert execute_query(sql, db).status == "blocked", f"NOT BLOCKED: {sql}"


@pytest.mark.parametrize("sql", HOSTILE, ids=[s[:28] for s in HOSTILE])
def test_blocked_even_without_keyword_filter(tmp_path, sql):
    """With the keyword filter disabled, the read-only connection and authorizer must block everything."""
    db = make_tiny_db(tmp_path)
    r = execute_query(sql, db, use_first_pass_filter=False)
    assert r.status == "blocked", f"LAYERS 2/3 FAILED: {sql} -> {r.status} {r.error}"


def test_database_is_unchanged_after_attack(tmp_path):
    """Check the data itself, not only the returned status."""
    db = make_tiny_db(tmp_path)
    execute_query("DROP TABLE students", db, use_first_pass_filter=False)
    execute_query("DELETE FROM students", db, use_first_pass_filter=False)
    after = execute_query("SELECT COUNT(*) FROM students", db)
    assert after.ok and after.rows == ((3,),)


def test_innocent_query_mentioning_a_banned_word_survives_layers_2_3(tmp_path):
    """The keyword filter produces false positives; the real controls do not."""
    db = make_tiny_db(tmp_path)
    sql = "SELECT name FROM students WHERE name != 'drop'"
    assert execute_query(sql, db).status == "blocked"  # keyword filter over-blocks
    assert execute_query(sql, db, use_first_pass_filter=False).ok  # read-only + authorizer allow it
