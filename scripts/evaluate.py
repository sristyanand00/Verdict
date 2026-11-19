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

Re-score a saved evaluation with other settings (no GPU, no model):
    python scripts/evaluate.py --rescore results/eval_sft.jsonl --label sft_t30 --timeout 30 --workers 4

Settings used for the reported numbers (keep them the same for every model):
    --max-schema-chars 12000 --timeout 30 --workers 4

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
from verdict.eval.metrics import wilson  # noqa: E402
from verdict.train.evaluation import OUTCOME, evaluate_tasks, score_texts  # noqa: E402
from verdict.train.modeling import amp_dtype, load_for_inference  # noqa: E402
from verdict.train.reward import SQLRewardFunction  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a model on BIRD dev",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--model", default=None, help="Hugging Face name, checkpoint folder or adapter folder")
    p.add_argument("--rescore", type=Path, default=None,
                   help="re-score the SQL in a saved eval_<label>.jsonl instead of generating (no model needed)")
    p.add_argument("--label", required=True, help="short name used in the output file names")
    p.add_argument("--max-tasks", type=int, default=None, help="evaluate only N questions (spread across databases)")
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--max-schema-chars", type=int, default=6000)
    p.add_argument("--timeout", type=float, default=5.0, help="seconds each query may run (reports use 30)")
    p.add_argument("--workers", type=int, default=8, help="queries run at the same time (reports use 4)")
    p.add_argument("--gen-batch", type=int, default=1, help="questions generated together; 8 suits a 12 GB GPU")
    p.add_argument("--baseline", type=Path, default=None, help="an earlier eval_<label>.jsonl to compare with")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args()
    if (args.model is None) == (args.rescore is None):
        p.error("give exactly one of --model or --rescore")
    return args


def load_saved_texts(path: Path, tasks: list) -> list[str]:
    """The SQL saved per question in an eval_<label>.jsonl, in ``tasks`` order."""
    saved = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            saved[r["question_id"]] = r.get("sql", "")
    missing = [t.question_id for t in tasks if t.question_id not in saved]
    if missing:
        raise ValueError(f"{path} has no answer for {len(missing)} questions, e.g. {missing[:5]}")
    return [saved[t.question_id] for t in tasks]


def print_summary(label: str, rows: list[dict]) -> dict:
    def line(name, subset):
        c = Counter(r["outcome"] for r in subset)
        n = len(subset)
        correct, ran = c[OUTCOME["correct"]], n - c[OUTCOME["failed"]]
        low, high = wilson(correct, n)
        print(f"  {name:12s} {n:5d} questions  correct {correct:5d} ({100 * correct / n:5.1f}%, "
              f"range {100 * low:.1f}-{100 * high:.1f})  ran {ran:5d} ({100 * ran / n:5.1f}%)")
        return {"questions": n, "correct": correct, "ran": ran, "accuracy": correct / n, "ran_rate": ran / n,
                "accuracy_low": low, "accuracy_high": high}

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

    reward_fn = SQLRewardFunction(db_root, timeout_s=args.timeout, workers=args.workers)
    if args.rescore:
        logger.info("Re-scoring %s on %d questions (timeout %.0fs, %d workers)",
                    args.rescore, len(tasks), args.timeout, args.workers)
        result = score_texts(load_saved_texts(args.rescore, tasks), tasks, reward_fn)
        source = f"rescore of {args.rescore}"
    else:
        logger.info("Loading %s", args.model)
        model, tokenizer = load_for_inference(args.model, args.device)
        schemas = SchemaStore(db_root, sample_rows=2, max_chars=args.max_schema_chars)
        prompts = [render_prompt(tokenizer, t, schemas(t.db_id)) for t in tasks]
        logger.info("Answering %d BIRD dev questions (timeout %.0fs, %d workers, batch %d, precision %s)",
                    len(tasks), args.timeout, args.workers, args.gen_batch,
                    amp_dtype() if args.device.startswith("cuda") else "fp32")
        result = evaluate_tasks(
            model, tokenizer, prompts, tasks, reward_fn, max_tokens=args.max_tokens,
            amp=args.device.startswith("cuda"), chunk=100, log=lambda m: print(m, flush=True),
            batch_size=args.gen_batch,
        )
        source = str(args.model)
    rows = result.rows(tasks)

    out = results_root()
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"eval_{args.label}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    summary = print_summary(f"{args.label} ({source})", rows)
    failures = result.failure_counts()
    if failures:
        print("\nWhy queries failed:")
        for reason, n in failures.most_common():
            print(f"  {reason:28s} {n}")
    gold_failed = sum(r["reason"].startswith("gold query failed") for r in rows)
    if gold_failed:
        print(f"\n{gold_failed} answers ran but were marked wrong because the gold query itself failed.")
    summary.update(model=source, seconds=result.seconds, failures=dict(failures), gold_failed=gold_failed,
                   settings={"max_schema_chars": args.max_schema_chars, "timeout_s": args.timeout,
                             "workers": args.workers, "max_tokens": args.max_tokens,
                             "gen_batch": args.gen_batch, "rescore": bool(args.rescore)})
    (out / f"eval_{args.label}_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nTook {result.seconds / 60:.1f} minutes. Saved {out / f'eval_{args.label}.jsonl'}")

    if args.baseline:
        compare(rows, args.baseline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
