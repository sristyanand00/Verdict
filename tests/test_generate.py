from verdict.engine.generate import CANNOT_ANSWER, build_prompt, generate_attempts, parse_reply
from verdict.engine.llm import FixedWriter


def test_prompt_contains_schema_question_and_way_out():
    p = build_prompt("sales(amount REAL)", "  Total sales?  ")
    assert "sales(amount REAL)" in p
    assert "Question: Total sales?" in p
    assert CANNOT_ANSWER in p


def test_reads_sql_from_code_block():
    a = parse_reply("Here you go:\n```sql\nSELECT 1\n```")
    assert (a.kind, a.sql) == ("sql", "SELECT 1")


def test_uses_last_block_when_model_drafts_first():
    a = parse_reply("```sql\nSELECT 1\n```\nBetter:\n```sql\nSELECT 2\n```")
    assert a.sql == "SELECT 2"


def test_cannot_answer_reply():
    assert parse_reply("CANNOT_ANSWER").kind == "cannot_answer"
    assert parse_reply("Sorry, CANNOT_ANSWER: no such column.").kind == "cannot_answer"
    assert parse_reply("```\nCANNOT_ANSWER\n```").kind == "cannot_answer"


def test_sql_wins_over_a_mention_of_cannot_answer():
    a = parse_reply("Not CANNOT_ANSWER, here:\n```sql\nSELECT 3\n```")
    assert (a.kind, a.sql) == ("sql", "SELECT 3")


def test_empty_reply():
    assert parse_reply("").kind == "empty"
    assert parse_reply(None).kind == "empty"


def test_generate_asks_writer_n_times():
    w = FixedWriter(["```sql\nSELECT 1\n```"])
    attempts = generate_attempts(w, "t(a INT)", "q?", n=5)
    assert len(attempts) == 5 and all(a.kind == "sql" for a in attempts)
    assert len(w.prompts) == 1
