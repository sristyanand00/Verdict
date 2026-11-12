import pytest

from tests.fixtures import make_tiny_db
from verdict.engine.ask import ask
from verdict.engine.llm import FixedWriter

T = {"green": 0.75, "yellow": 0.5, "cannot_answer": 0.5}


def block(q):
    return f"```sql\n{q}\n```"


def test_end_to_end_green(tmp_path):
    db = make_tiny_db(tmp_path)
    w = FixedWriter([block("SELECT COUNT(*) FROM students")] * 7 + [block("SELECT 99")])
    a = ask(db, "How many students?", writer=w, thresholds=T)
    assert a.level == "green" and a.shown
    assert a.rows == ((3,),)
    assert a.sql == "SELECT COUNT(*) FROM students"
    assert "students(id INTEGER" in w.prompts[0]


def test_end_to_end_red_hides_answer(tmp_path):
    db = make_tiny_db(tmp_path)
    w = FixedWriter([block(f"SELECT {i}") for i in range(8)])
    a = ask(db, "q?", writer=w, thresholds=T)
    assert a.level == "red" and not a.shown and a.rows == () and a.sql == ""


def test_end_to_end_unanswerable(tmp_path):
    db = make_tiny_db(tmp_path)
    a = ask(db, "How happy are students?", writer=FixedWriter(["CANNOT_ANSWER"]), thresholds=T)
    assert a.level == "unanswerable"


def test_empty_question_rejected(tmp_path):
    with pytest.raises(ValueError):
        ask(make_tiny_db(tmp_path), "  ", writer=FixedWriter(["x"]))
