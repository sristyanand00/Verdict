#!/usr/bin/env python
"""Train a text-to-SQL model with GRPO on BIRD dev.

Usage:
    python scripts/train_grpo.py                                # defaults (fits a 16 GB T4)
    python scripts/train_grpo.py --num-tasks 16 --epochs 1      # quick smoke run
    python scripts/train_grpo.py --checkpoint-dir /kaggle/working/checkpoints

Environment:
    VERDICT_DATA_ROOT     folder holding dev.json and dev_databases/ (default: datasets/)
    VERDICT_RESULTS_ROOT  where training_results.json is written (default: results/)
    CUDA_VISIBLE_DEVICES  GPUs to use (only the first is used)

Note: BIRD dev is also BIRD's evaluation set. A model trained on it cannot be
scored on BIRD dev; use this for development, and BIRD train for real results.
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import data_root, results_root  # noqa: E402
from verdict.data.loaders import load_bird_dev  # noqa: E402
from verdict.train.batch import create_train_val_split, stratified_train_val_split  # noqa: E402
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
DEFAULTS = GRPOTrainingConfig()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train text-to-SQL model with GRPO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--model", default=DEFAULTS.model_name, help="Hugging Face model name")
    p.add_argument("--epochs", type=int, default=DEFAULTS.num_epochs)
    p.add_argument("--batch-size", type=int, default=DEFAULTS.batch_size, help="questions per batch")
    p.add_argument("--lr", type=float, default=DEFAULTS.learning_rate, help="learning rate")
    p.add_argument("--num-generations", type=int, default=DEFAULTS.num_generations, help="completions per question")
    p.add_argument("--max-tokens", type=int, default=DEFAULTS.max_tokens, help="max new tokens per completion")
    p.add_argument("--temperature", type=float, default=DEFAULTS.temperature)
    p.add_argument("--gradient-accumulation-steps", type=int, default=DEFAULTS.gradient_accumulation_steps)
    p.add_argument("--micro-batch-size", type=int, default=DEFAULTS.micro_batch_size,
                   help="completions per forward/backward; lower it if you run out of GPU memory")
    p.add_argument("--eval-max-tasks", type=int, default=DEFAULTS.eval_max_tasks,
                   help="validation questions evaluated per epoch")
    p.add_argument("--checkpoint-dir", default="checkpoints")
    p.add_argument("--num-tasks", type=int, default=None, help="use only N tasks (sampled across databases)")
    p.add_argument("--train-ratio", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=DEFAULTS.seed)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--no-stratified", action="store_true", help="split without preserving difficulty mix")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU (this will be very slow)")
        args.device = "cpu"

    try:
        all_tasks = load_bird_dev(data_root=data_root())
    except FileNotFoundError as e:
        logger.error("Failed to load BIRD: %s", e)
        logger.error("Set VERDICT_DATA_ROOT to the folder holding dev.json and dev_databases/")
        return 1

    if args.num_tasks:
        # BIRD dev is sorted by database, so the first N would all be one or two
        # databases. Take every k-th task instead to keep the variety.
        step = max(len(all_tasks) // args.num_tasks, 1)
        all_tasks = all_tasks[::step][: args.num_tasks]
    distribution = dict(Counter(t.difficulty for t in all_tasks))
    logger.info("Loaded %d tasks: %s", len(all_tasks), distribution)

    split = create_train_val_split if args.no_stratified else stratified_train_val_split
    train_tasks, val_tasks = split(all_tasks, args.train_ratio)
    logger.info("Train: %d tasks, val: %d tasks", len(train_tasks), len(val_tasks))

    config = GRPOTrainingConfig(
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        num_generations=args.num_generations,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        micro_batch_size=args.micro_batch_size,
        eval_max_tasks=args.eval_max_tasks,
        seed=args.seed,
        checkpoint_dir=Path(args.checkpoint_dir),
        device=args.device,
    )
    trainer = GRPOTrainer(config=config, db_root=data_root() / "dev_databases")

    start = time.time()
    result = trainer.fit(train_tasks, val_tasks)
    elapsed = time.time() - start
    metrics = result["metrics"]

    results_path = results_root() / "training_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "config": vars(args),
                "data": {
                    "total_tasks": len(all_tasks),
                    "train_tasks": len(train_tasks),
                    "val_tasks": len(val_tasks),
                    "distribution": distribution,
                },
                "training": {"duration_s": elapsed, **result},
            },
            indent=2,
        )
    )

    logger.info("Training finished in %.1f minutes", elapsed / 60)
    if metrics["reward_mean"]:
        logger.info(
            "Reward: first epoch %.4f, last epoch %.4f", metrics["reward_mean"][0], metrics["reward_mean"][-1]
        )
    if result["val_accuracy_before"] is not None:
        logger.info(
            "Validation accuracy: %.1f%% before, best %.1f%% after",
            100 * result["val_accuracy_before"], 100 * result["best_val_accuracy"],
        )
    logger.info("Results: %s", results_path)
    logger.info("Checkpoints: %s (latest/ and best/)", result["checkpoint_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
