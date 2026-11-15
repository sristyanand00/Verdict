#!/usr/bin/env python
"""Execution accuracy of one model on BIRD dev.

Usage:
    python scripts/evaluate.py --model Qwen/Qwen2.5-Coder-1.5B-Instruct --label base
    python scripts/evaluate.py --model /path/to/sft/best --label sft --baseline results/eval_base.jsonl

--model is a Hugging Face name, a full checkpoint folder, or a LoRA adapter
folder (merged into its base model). One greedy answer per question.

Writes to VERDICT_RESULTS_ROOT (default results/):
    eval_<label>.jsonl         one line per question: id, database, difficulty, outcome, SQL
    eval_<label>_summary.json  accuracy overall and per difficulty

With --baseline, also prints how each question moved compared with an
earlier eval_<label>.jsonl, and lists the questions that became correct or
stopped being correct.

Environment:
    VERDICT_DATA_ROOT     folder holding dev.json and dev_databases/
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import data_root, results_root  # noqa: E402
from verdict.data.loaders import DIFFICULTIES, load_bird_dev  # noqa: E402
from verdict.train.data_prep import SchemaStore, render_prompt  # noqa: E402
from verdict.train.evaluation import OUTCOME, evaluate_tasks  # noqa: E402
from verdict.train.modeling import load_for_inference  # noqa: E402
from verdict.train.reward import SQLRewardFunction  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a model on BIRD dev",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--model", required=True, help="Hugging Face name, checkpoint folder or adapter folder")
    p.add_argument("--label", required=True, help="short name used in the output file names")
    p.add_argument("--max-tasks", type=int, default=None, help="evaluate only N questions (spread across databases)")
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--max-schema-chars", type=int, default=6000)
    p.add_argument("--baseline", type=Path, default=None, help="an earlier eval_<label>.jsonl to compare with")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()


def print_summary(label: str, rows: list[dict]) -> dict:
    def line(name, subset):
        c = Counter(r["outcome"] for r in subset)
        n = len(subset)
        correct, ran = c[OUTCOME["correct"]], n - c[OUTCOME["failed"]]
        print(f"  {name:12s} {n:5d} questions  correct {correct:5d} ({100 * correct / n:5.1f}%)  "
              f"ran {ran:5d} ({100 * ran / n:5.1f}%)")
        return {"questions": n, "correct": correct, "ran": ran, "accuracy": correct / n, "ran_rate": ran / n}

    print(f"\n{label}")
    summary = {"overall": line("overall", rows)}
    for d in DIFFICULTIES:
        subset = [r for r in rows if r["difficulty"] == d]
        if subset:
            summary[d] = line(d, subset)
    return summary


def compare(rows: list[dict], baseline_path: Path) -> None:
    base = {}
    with open(baseline_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            base[r["question_id"]] = r
    common = [r for r in rows if r["question_id"] in base]
    print(f"\nCompared with {baseline_path.name} on {len(common)} shared questions (baseline -> this model):")
    moves = Counter((base[r["question_id"]]["outcome"], r["outcome"]) for r in common)
    for (b, a), n in moves.most_common():
        print(f"  {b:11s} -> {a:11s} {n}")
    correct = OUTCOME["correct"]
    gained = [r for r in common if r["outcome"] == correct and base[r["question_id"]]["outcome"] != correct]
    lost = [r for r in common if r["outcome"] != correct and base[r["question_id"]]["outcome"] == correct]
    print(f"\nBecame correct: {len(gained)}   Stopped being correct: {len(lost)}   Net: {len(gained) - len(lost):+d}")


def main() -> int:
    args = parse_args()
    tasks = load_bird_dev(data_root=data_root())
    if args.max_tasks and args.max_tasks < len(tasks):
        step = len(tasks) // args.max_tasks
        tasks = tasks[::step][: args.max_tasks]
    db_root = data_root() / "dev_databases"

    logger.info("Loading %s", args.model)
    model, tokenizer = load_for_inference(args.model, args.device)
    schemas = SchemaStore(db_root, sample_rows=2, max_chars=args.max_schema_chars)
    prompts = [render_prompt(tokenizer, t, schemas(t.db_id)) for t in tasks]
    reward_fn = SQLRewardFunction(db_root)

    logger.info("Answering %d BIRD dev questions", len(tasks))
    result = evaluate_tasks(
        model, tokenizer, prompts, tasks, reward_fn, max_tokens=args.max_tokens,
        amp=args.device.startswith("cuda"), chunk=100, log=lambda m: print(m, flush=True),
    )
    rows = result.rows(tasks)

    out = results_root()
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"eval_{args.label}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    summary = print_summary(f"{args.label} ({args.model})", rows)
    failures = result.failure_counts()
    if failures:
        print("\nWhy queries failed:")
        for reason, n in failures.most_common():
            print(f"  {reason:28s} {n}")
    gold_failed = sum(r["reason"].startswith("gold query failed") for r in rows)
    if gold_failed:
        print(f"\n{gold_failed} answers ran but were marked wrong because the gold query itself failed.")
    summary.update(model=str(args.model), seconds=result.seconds,
                   failures=dict(failures), gold_failed=gold_failed)
    (out / f"eval_{args.label}_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nTook {result.seconds / 60:.1f} minutes. Saved {out / f'eval_{args.label}.jsonl'}")

    if args.baseline:
        compare(rows, args.baseline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
