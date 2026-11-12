import sqlite3

from tests.fixtures import make_tiny_db
from verdict.data.loaders import BirdTask
from verdict.data.unanswerable import gold_tables, make_unanswerable


def task(db, qid, sql):
    return BirdTask(qid, "tiny", "Who scored highest?", "", sql, "simple", db)


def test_gold_tables_ignores_ctes_and_aliases():
    sql = "WITH t AS (SELECT * FROM marks) SELECT s.name FROM students AS s JOIN t ON t.student_id = s.id"
    assert gold_tables(sql) == {"marks", "students"}


def test_drops_the_tables_the_question_needs(tmp_path):
    db = make_tiny_db(tmp_path / "dbs")
    out = make_unanswerable([task(db, 1, "SELECT name FROM students")], k=5, out_root=tmp_path / "u")
    assert len(out) == 1
    u = out[0]
    assert u.gold_sql == "" and u.question == "Who scored highest?" and u.db_path != db
    tables = [r[0] for r in sqlite3.connect(u.db_path).execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert tables == ["marks"]
    # the original is untouched
    assert "students" in [r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master")]


def test_skips_questions_that_would_leave_no_tables(tmp_path):
    db = make_tiny_db(tmp_path / "dbs")
    t = task(db, 2, "SELECT name FROM students JOIN marks ON marks.student_id = students.id")
    assert make_unanswerable([t], k=5, out_root=tmp_path / "u") == []
