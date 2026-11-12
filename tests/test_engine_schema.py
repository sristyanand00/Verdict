import sqlite3

import pytest

from tests.fixtures import make_tiny_db
from verdict.engine.schema import describe_schema


def test_describes_every_table_and_column(tmp_path):
    db = make_tiny_db(tmp_path)
    assert describe_schema(db) == (
        "marks(id INTEGER, student_id INTEGER, subject TEXT, score REAL)\n"
        "students(id INTEGER, name TEXT, year INTEGER)"
    )


def test_never_includes_row_values(tmp_path):
    db = make_tiny_db(tmp_path)
    text = describe_schema(db)
    for value in ("Priya", "Rahul", "DBMS", "94"):
        assert value not in text


def test_quotes_names_that_need_it(tmp_path):
    db = tmp_path / "odd.sqlite"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "Sales Data" ("Order Date" TEXT, amount REAL)')
    con.close()
    assert describe_schema(db) == '"Sales Data"("Order Date" TEXT, amount REAL)'


def test_quotes_sql_keywords(tmp_path):
    # BIRD's financial database has a table called "order".
    db = tmp_path / "kw.sqlite"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "order" ("group" TEXT, amount REAL)')
    con.close()
    assert describe_schema(db) == '"order"("group" TEXT, amount REAL)'


def test_missing_and_empty_databases_raise(tmp_path):
    with pytest.raises(FileNotFoundError):
        describe_schema(tmp_path / "nope.sqlite")
    empty = tmp_path / "empty.sqlite"
    sqlite3.connect(empty).close()
    with pytest.raises(ValueError):
        describe_schema(empty)
