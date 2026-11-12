"""Run the trust engine on BIRD questions and record what happened.

    evaluate(tasks, writer, out_path, n=8) -> list of records

For each question this does exactly what the product does (schema -> n
attempts -> run and group), then also runs BIRD's gold SQL and checks every
attempt and every group against it. Nothing about trust levels is decided
here: records hold raw counts, and eval/calibration.py applies the rules
later. That way thresholds can be changed and re-scored without calling the
AI again.

Records are appended to a JSONL file one question at a time. If the run stops
(quota, network, Ctrl+C), running it again skips questions already done.

One record:
    question_id, db_id, difficulty, answerable
    n, n_cannot, n_failed
    attempt_correct  list per attempt: true / false / null (no result)
    group_sizes      largest first
    group_correct    per group: true / false (null when unanswerable)
    top_empty        largest group's answer is empty or all NULL
    gold_status      "ok", or why the gold query failed (record then skipped)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from verdict.data.loaders import BirdTask
from verdict.engine.generate import build_prompt, parse_reply
from verdict.engine.group import run_and_group
from verdict.engine.llm import SQLWriter
from verdict.engine.schema import describe_schema
from verdict.verifier.compare import compare_results
from verdict.verifier.pool import execute_isolated

log = logging.getLogger(__name__)

#: BIRD queries on the bigger databases can take seconds; the product's 5 s
#: limit would count slow-but-correct attempts as failures.
ATTEMPT_TIMEOUT_S = 20.0
GOLD_TIMEOUT_S = 60.0


def _key(task: BirdTask, answerable: bool) -> str:
    return f"{'A' if answerable else 'U'}:{task.question_id}"


def load_records(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate_one(task: BirdTask, writer: SQLWriter, n: int = 8, answerable: bool = True) -> dict:
    """Run one question through the engine and score it against gold."""
    prompt = build_prompt(describe_schema(task.db_path), task.question, hint=task.evidence)
    attempts = [parse_reply(r) for r in writer.write(prompt, n)]
    g = run_and_group(attempts, task.db_path, timeout_s=ATTEMPT_TIMEOUT_S)

    rec = {
        "key": _key(task, answerable),
        "question_id": task.question_id,
        "db_id": task.db_id,
        "difficulty": task.difficulty,
        "answerable": answerable,
        "n": n,
        "n_cannot": g.n_cannot_answer,
        "n_failed": g.n_failed,
        "group_sizes": [grp.size for grp in g.groups],
        "top_empty": bool(g.top and g.top.is_empty_answer),
        "sqls": [a.sql or a.kind for a in attempts],
    }

    if not answerable:
        rec.update(gold_status="none", attempt_correct=[None] * n, group_correct=[None] * len(g.groups))
        return rec

    gold = execute_isolated(task.gold_sql, task.db_path, timeout_s=GOLD_TIMEOUT_S)
    rec["gold_status"] = gold.status
    if not gold.ok:
        rec.update(attempt_correct=[None] * n, group_correct=[None] * len(g.groups))
        return rec

    def correct(result) -> bool:
        return compare_results(result, gold, task.gold_sql).verdict == "correct"

    rec["attempt_correct"] = [
        (correct(r) if r is not None and r.ok else None) for r in g.results
    ]
    rec["group_correct"] = [correct(grp.result) for grp in g.groups]
    return rec


def evaluate(
    tasks: list[BirdTask],
    writer: SQLWriter,
    out_path: str | Path,
    n: int = 8,
    answerable: bool = True,
) -> list[dict]:
    """Evaluate every task not already in ``out_path``; return all records.

    Exceptions from the writer (e.g. LLMError when the quota runs out) stop
    the run after saving everything finished so far.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["key"] for r in load_records(out_path)}
    todo = [t for t in tasks if _key(t, answerable) not in done]
    log.info("%d done, %d to run -> %s", len(done), len(todo), out_path)

    with out_path.open("a", encoding="utf-8") as f:
        for i, task in enumerate(todo, 1):
            rec = evaluate_one(task, writer, n, answerable)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            top = rec["group_sizes"][0] if rec["group_sizes"] else 0
            ok = rec["group_correct"][0] if rec["group_correct"] else None
            print(f"  [{i}/{len(todo)}] {rec['key']:>7} {task.db_id[:24]:<24} "
                  f"top {top}/{n} refused {rec['n_cannot']} failed {rec['n_failed']} "
                  f"top-correct={ok}", flush=True)
    return load_records(out_path)
