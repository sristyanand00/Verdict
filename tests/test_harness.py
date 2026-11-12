from tests.fixtures import make_tiny_db
from verdict.data.loaders import BirdTask
from verdict.engine.llm import FixedWriter
from verdict.eval.harness import evaluate, evaluate_one


def block(q):
    return f"```sql\n{q}\n```"


def test_scores_every_attempt_and_group_against_gold(tmp_path):
    db = make_tiny_db(tmp_path)
    t = BirdTask(7, "tiny", "How many students?", "", "SELECT COUNT(*) FROM students", "simple", db)
    w = FixedWriter([block("SELECT COUNT(*) FROM students")] * 6
                    + [block("SELECT 99"), block("SELECT nope FROM students")])
    r = evaluate_one(t, w, n=8)
    assert r["gold_status"] == "ok"
    assert r["group_sizes"] == [6, 1] and r["group_correct"] == [True, False]
    assert r["attempt_correct"] == [True] * 6 + [False, None]
    assert r["n_failed"] == 1


def test_resumes_without_redoing_finished_questions(tmp_path):
    db = make_tiny_db(tmp_path)
    tasks = [BirdTask(i, "tiny", "q", "", "SELECT 1", "simple", db) for i in range(3)]
    w = FixedWriter([block("SELECT 1")])
    out = tmp_path / "r.jsonl"
    evaluate(tasks[:2], w, out, n=2)
    calls_before = len(w.prompts)
    recs = evaluate(tasks, w, out, n=2)
    assert len(recs) == 3 and len(w.prompts) == calls_before + 1
