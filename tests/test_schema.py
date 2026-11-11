import sqlite3

import pytest

from tests.fixtures import make_tiny_db
from verdict.data.schema import get_schema, get_schema_cached


def test_schema_has_tables_and_samples(tmp_path):
    schema = get_schema(make_tiny_db(tmp_path), num_samples=2)
    assert "CREATE TABLE students" in schema
    assert "CREATE TABLE marks" in schema
    assert "-- (1, 'Priya', 2)" in schema
    assert "'Aisha'" not in schema  # only 2 sample rows per table


def test_awkward_table_name_and_empty_table(tmp_path):
    db = tmp_path / "odd.sqlite"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "order details" (x INTEGER)')
    con.commit()
    con.close()
    schema = get_schema(db)
    assert "Error" not in schema
    assert "-- (empty table)" in schema


def test_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_schema(tmp_path / "nope.sqlite")


def test_cache_is_written_and_reused(tmp_path):
    db = make_tiny_db(tmp_path / "dbs")
    cache = tmp_path / "cache"
    first = get_schema_cached(db, cache_dir=cache)
    cache_file = cache / "tiny.schema.txt"
    assert cache_file.read_text(encoding="utf-8") == first
    cache_file.write_text("cached", encoding="utf-8")
    assert get_schema_cached(db, cache_dir=cache) == "cached"
