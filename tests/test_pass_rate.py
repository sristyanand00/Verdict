"""Resume safety of scripts/pass_rate.py: broken last lines after a power cut."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("torch")

_SPEC = importlib.util.spec_from_file_location(
    "pass_rate_script", Path(__file__).resolve().parent.parent / "scripts" / "pass_rate.py")
pass_rate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pass_rate)


def _line(qid: int, correct: int) -> str:
    return json.dumps({"question_id": qid, "db_id": "db", "correct": correct, "of": 8})


def test_clean_file_is_read_and_left_alone(tmp_path):
    f = tmp_path / "pass_rates.jsonl"
    text = _line(1, 3) + "\n" + _line(2, 0) + "\n"
    f.write_text(text, encoding="utf-8")
    done, dropped = pass_rate.read_done(f)
    assert done == {1: 3, 2: 0}
    assert dropped == 0
    assert f.read_text(encoding="utf-8") == text


def test_half_written_last_line_is_dropped_and_file_repaired(tmp_path):
    f = tmp_path / "pass_rates.jsonl"
    f.write_text(_line(1, 3) + "\n" + _line(2, 8) + "\n" + '{"question_id": 3, "db_', encoding="utf-8")
    done, dropped = pass_rate.read_done(f)
    assert done == {1: 3, 2: 8}
    assert dropped == 1
    assert f.read_text(encoding="utf-8") == _line(1, 3) + "\n" + _line(2, 8) + "\n"
    # The next append starts on its own line.
    with open(f, "a", encoding="utf-8") as out:
        out.write(_line(3, 5) + "\n")
    assert pass_rate.read_done(f) == ({1: 3, 2: 8, 3: 5}, 0)


def test_zero_bytes_at_the_end_are_ignored(tmp_path):
    f = tmp_path / "pass_rates.jsonl"
    f.write_bytes((_line(1, 4) + "\n").encode("utf-8") + b"\x00" * 50)
    done, dropped = pass_rate.read_done(f)
    assert done == {1: 4}
    assert dropped == 0
    assert f.read_text(encoding="utf-8") == _line(1, 4) + "\n"


def test_good_last_line_without_newline_gets_one(tmp_path):
    f = tmp_path / "pass_rates.jsonl"
    f.write_text(_line(1, 2) + "\n" + _line(2, 6), encoding="utf-8")
    done, dropped = pass_rate.read_done(f)
    assert done == {1: 2, 2: 6}
    assert dropped == 0
    assert f.read_text(encoding="utf-8").endswith(_line(2, 6) + "\n")
