#!/usr/bin/env python
"""Pick the BIRD train questions that GRPO can learn from.

GRPO learns only from questions where some of the model's answers are right
and some are wrong. If all 8 answers score the same, every advantage is zero
and the question costs GPU time while teaching nothing (Phase 1, step 4).

This script samples ``--num-samples`` answers per question with the given
model (usually the SFT result), counts how many are correct, and keeps the
questions solved sometimes but not always.

Usage:
    python scripts/pass_rate.py --train-dir /path/to/bird_train \\
        --model /path/to/sft/best --num-tasks 2000 --out /kaggle/working/grpo_tasks

Writes to --out:
    pass_rates.jsonl  one line per question: id, database, correct answers out of N
    kept_ids.json     ids with 0 < correct < N, for train_grpo.py --task-ids

Progress is saved after every chunk, so a run stopped by --time-limit-hours
(or by Kaggle) can be continued with the same command plus --resume.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.data.loaders import has_database, load_bird_train  # noqa: E402
from verdict.train.batch import holdout_split  # noqa: E402
from verdict.train.data_prep import SchemaStore, render_prompt  # noqa: E402
from verdict.train.grpo_utils import repeat_per_group  # noqa: E402
from verdict.train.modeling import load_for_inference  # noqa: E402
from verdict.train.reward import SQLRewardFunction  # noqa: E402
from verdict.train.rollout import GenerationConfig, generate_ids  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Measure per-question pass rates on BIRD train",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--train-dir", type=Path, required=True)
    p.add_argument("--model", required=True, help="model name, checkpoint or adapter folder")
    p.add_argument("--out", type=Path, required=True, help="output folder")
    p.add_argument("--num-samples", type=int, default=8, help="answers per question (use GRPO's group size)")
    p.add_argument("--temperature", type=float, default=0.9, help="use GRPO's temperature")
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--max-schema-chars", type=int, default=6000,
                   help="schema text limit in characters; use the same value for SFT, pass rate, GRPO and evaluation")
    p.add_argument("--gen-batch", type=int, default=1,
                   help="questions generated together (each with --num-samples answers); 2 suits a 12 GB GPU")
    p.add_argument("--num-tasks", type=int, default=None, help="measure only N questions (spread across databases)")
    p.add_argument("--val-size", type=int, default=200, help="must match SFT/GRPO, so held-out questions are skipped")
    p.add_argument("--split-seed", type=int, default=0)
    p.add_argument("--chunk", type=int, default=16, help="questions per save")
    p.add_argument("--time-limit-hours", type=float, default=None)
    p.add_argument("--resume", action="store_true", help="skip questions already in pass_rates.jsonl")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start = time.time()
    db_root = args.train_dir / "train_databases"
    tasks = load_bird_train(args.train_dir / "train_all.json", db_root)
    train, _ = holdout_split(tasks, args.val_size, seed=args.split_seed, eligible=has_database)
    train = [t for t in train if has_database(t)]
    if args.num_tasks and args.num_tasks < len(train):
        step = len(train) // args.num_tasks
        train = train[::step][: args.num_tasks]

    args.out.mkdir(parents=True, exist_ok=True)
    rates_file = args.out / "pass_rates.jsonl"
    done: dict[int, int] = {}
    if args.resume and rates_file.exists():
        for line in rates_file.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done[r["question_id"]] = r["correct"]
    elif rates_file.exists():
        rates_file.unlink()
    todo = [t for t in train if t.question_id not in done]
    logger.info("%d questions to measure (%d already done), %d answers each", len(todo), len(done), args.num_samples)

    model, tokenizer = load_for_inference(args.model, args.device)
    schemas = SchemaStore(db_root, args.train_dir / "schemas.json", max_chars=args.max_schema_chars)
    reward_fn = SQLRewardFunction(db_root)
    n = args.num_samples
    config = GenerationConfig(temperature=args.temperature, max_tokens=args.max_tokens)
    amp = args.device.startswith("cuda")

    stopped = False
    for i in range(0, len(todo), args.chunk):
        chunk = todo[i : i + args.chunk]
        prompts = [render_prompt(tokenizer, t, schemas(t.db_id)) for t in chunk]
        rollouts = generate_ids(model, tokenizer, prompts, n_completions=n, config=config, amp=amp,
                                batch_size=args.gen_batch)
        scores = reward_fn(
            prompts=repeat_per_group(prompts, n),
            completions=[text for r in rollouts for text in r.texts],
            gold_sql=repeat_per_group([t.gold_sql for t in chunk], n),
            db_id=repeat_per_group([t.db_id for t in chunk], n),
        )
        with open(rates_file, "a", encoding="utf-8") as f:
            for j, t in enumerate(chunk):
                correct = sum(s == reward_fn.rewards["correct"] for s in scores[j * n : (j + 1) * n])
                done[t.question_id] = correct
                f.write(json.dumps({"question_id": t.question_id, "db_id": t.db_id, "correct": correct, "of": n}) + "\n")
        elapsed = time.time() - start
        measured = i + len(chunk)
        print(f"  measured {measured}/{len(todo)} ({elapsed / 60:.0f} min, "
              f"about {elapsed / measured * (len(todo) - measured) / 60:.0f} min left)", flush=True)
        if args.time_limit_hours and elapsed > args.time_limit_hours * 3600:
            logger.info("Time limit reached; rerun with --resume to continue.")
            stopped = True
            break

    kept = sorted(q for q, c in done.items() if 0 < c < n)
    (args.out / "kept_ids.json").write_text(json.dumps(kept))
    never = sum(c == 0 for c in done.values())
    always = sum(c == n for c in done.values())
    print(f"\nMeasured {len(done)} questions: never solved {never}, always solved {always}, "
          f"sometimes solved {len(kept)} (kept for GRPO)")
    print(f"Saved {rates_file} and {args.out / 'kept_ids.json'}")
    return 2 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
