import json
from pathlib import Path

from tests.fixtures import make_tiny_db
from verdict.data.loaders import BirdTask
from verdict.train.data_prep import build_prompt, load_examples, prepare_training_data, save_examples


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
