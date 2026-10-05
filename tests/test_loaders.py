import json
from collections import Counter

import pytest

from tests.fixtures import make_tiny_db
from verdict import config
from verdict.data.loaders import BirdTask, load_bird_dev

ITEM = {
    "question_id": 0,
    "db_id": "tiny",
    "question": "  Which students are in year 2? ",
    "evidence": "",
    "SQL": "SELECT name FROM students WHERE year = 2\n",
    "difficulty": "simple",
}


def write_dev(tmp_path, items):
    p = tmp_path / "dev.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    return p


def bird_layout(tmp_path):
    """tmp_path/dev_databases/tiny/tiny.sqlite, the same layout as BIRD."""
    make_tiny_db(tmp_path / "dev_databases")
    return tmp_path


def test_loads_one_task(tmp_path):
    root = bird_layout(tmp_path)
    [t] = load_bird_dev(write_dev(tmp_path, [ITEM]), data_root=root)
    assert isinstance(t, BirdTask)
    assert t.question == "Which students are in year 2?"  # whitespace trimmed
    assert t.gold_sql == "SELECT name FROM students WHERE year = 2"
    assert t.db_path == root / "dev_databases" / "tiny" / "tiny.sqlite"
    assert t.db_path.exists()


def test_missing_field_is_rejected(tmp_path):
    bad = {k: v for k, v in ITEM.items() if k != "SQL"}
    with pytest.raises(ValueError, match="missing"):
        load_bird_dev(write_dev(tmp_path, [bad]), data_root=bird_layout(tmp_path))


def test_unknown_difficulty_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="difficulty"):
        load_bird_dev(write_dev(tmp_path, [{**ITEM, "difficulty": "easy"}]), data_root=bird_layout(tmp_path))


def test_duplicate_question_id_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_bird_dev(write_dev(tmp_path, [ITEM, ITEM]), data_root=bird_layout(tmp_path))


def test_missing_database_is_reported(tmp_path):
    item = {**ITEM, "db_id": "no_such_db"}
    with pytest.raises(FileNotFoundError, match="no_such_db"):
        load_bird_dev(write_dev(tmp_path, [item]), data_root=bird_layout(tmp_path))


def test_check_db_can_be_skipped(tmp_path):
    item = {**ITEM, "db_id": "no_such_db"}
    [t] = load_bird_dev(write_dev(tmp_path, [item]), data_root=tmp_path, check_db=False)
    assert not t.db_path.exists()


@pytest.mark.skipif(not config.dev_json().exists(), reason="BIRD dev set not downloaded")
def test_real_bird_dev():
    tasks = load_bird_dev()
    assert len(tasks) == 1534
    assert len({t.db_id for t in tasks}) == 11
    assert Counter(t.difficulty for t in tasks) == {"simple": 925, "moderate": 464, "challenging": 145}
