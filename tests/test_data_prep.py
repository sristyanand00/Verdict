import json
from pathlib import Path

import pytest

from tests.fixtures import make_tiny_db
from verdict.data.loaders import BirdTask
from verdict.train.data_prep import (
    SchemaStore,
    build_prompt,
    load_examples,
    prepare_training_data,
    save_examples,
    shorten_schema,
    sql_answer,
)


def task(db_id="tiny", evidence="year means school year"):
    return BirdTask(
        question_id=7,
        db_id=db_id,
        question="Who is in year 2?",
        evidence=evidence,
        gold_sql="SELECT name FROM students WHERE year = 2",
        difficulty="simple",
        db_path=Path("unused"),
    )


def test_prompt_contains_schema_question_and_hint():
    system, user = build_prompt(task(), "CREATE TABLE t (x);")
    assert system["role"] == "system" and "SELECT" in system["content"]
    assert "CREATE TABLE t (x);" in user["content"]
    assert "Who is in year 2?" in user["content"]
    assert "### Hint\nyear means school year" in user["content"]


def test_hint_can_be_left_out():
    _, user = build_prompt(task(), "schema", include_evidence=False)
    assert "Hint" not in user["content"]
    _, user = build_prompt(task(evidence=""), "schema")
    assert "Hint" not in user["content"]


def test_prepare_skips_missing_databases_and_round_trips(tmp_path):
    make_tiny_db(tmp_path)
    examples = prepare_training_data([task(), task(db_id="missing")], db_root=tmp_path)
    assert [e.db_id for e in examples] == ["tiny"]
    assert "CREATE TABLE students" in examples[0].prompt[1]["content"]

    out = tmp_path / "out" / "examples.json"
    save_examples(examples, out)
    [row] = load_examples(out)
    assert row["gold_sql"] == task().gold_sql
    assert row["prompt"] == json.loads(json.dumps(examples[0].prompt))


def test_schema_store_prefers_the_database_and_falls_back_to_the_saved_file(tmp_path):
    make_tiny_db(tmp_path / "dbs")
    saved = tmp_path / "schemas.json"
    saved.write_text(json.dumps({
        "tiny": {"with_rows": "SAVED", "no_rows": "SAVED"},
        "big": {"with_rows": "CREATE TABLE big (x);\n-- Sample rows:\n-- (1,)", "no_rows": "CREATE TABLE big (x);"},
    }))
    store = SchemaStore(tmp_path / "dbs", saved, sample_rows=2, max_chars=6000)
    assert "CREATE TABLE students" in store("tiny")  # read from the database, not "SAVED"
    assert "-- (1,)" in store("big")
    assert SchemaStore(None, saved, sample_rows=0)("big") == "CREATE TABLE big (x);"
    with pytest.raises(FileNotFoundError):
        store("nowhere")


def test_shorten_schema_drops_rows_first_then_cuts():
    with_rows = "CREATE TABLE a (x);\n-- Sample rows:\n-- (1,)\n"
    assert shorten_schema(with_rows, "CREATE TABLE a (x);", 1000) == with_rows
    assert shorten_schema(with_rows, "CREATE TABLE a (x);", 25) == "CREATE TABLE a (x);"
    long = "line one\nline two\nline three"
    assert shorten_schema(long, long, 15) == "line one\n-- (schema truncated)"


def test_sql_answer_is_one_fenced_block():
    assert sql_answer("  SELECT 1 \n") == "```sql\nSELECT 1\n```"
