#!/usr/bin/env python
"""Train a text-to-SQL model with GRPO on BIRD dev.

Usage:
    python scripts/train_grpo.py --model Qwen/Qwen2.5-0.5B-Instruct --epochs 3 --batch-size 8
    python scripts/train_grpo.py --num-tasks 16 --epochs 1      # quick smoke run

Environment:
    VERDICT_DATA_ROOT     folder holding dev.json and dev_databases/ (default: datasets/)
    CUDA_VISIBLE_DEVICES  GPUs to use
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train text-to-SQL model with GRPO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct", help="Hugging Face model name")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-5, help="learning rate")
    p.add_argument("--num-generations", type=int, default=8, help="completions per prompt (group size)")
    p.add_argument("--max-tokens", type=int, default=256, help="max new tokens per completion")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--gradient-accumulation-steps", type=int, default=2)
    p.add_argument("--checkpoint-dir", default="checkpoints")
    p.add_argument("--num-tasks", type=int, default=None, help="use only the first N tasks")
    p.add_argument("--train-ratio", type=float, default=0.8)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--no-stratified", action="store_true", help="split without preserving difficulty mix")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU")
        args.device = "cpu"
    if args.device == "cuda":
        props = torch.cuda.get_device_properties(0)
        logger.info("GPU: %s (%.1f GB)", props.name, props.total_memory / 1e9)

    try:
        all_tasks = load_bird_dev(data_root=data_root())
    except FileNotFoundError as e:
        logger.error("Failed to load BIRD: %s", e)
        logger.error("Run: powershell -ExecutionPolicy Bypass -File scripts\fetch_bird.ps1")
        return 1

    if args.num_tasks:
        all_tasks = all_tasks[: args.num_tasks]
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
        checkpoint_dir=Path(args.checkpoint_dir),
        device=args.device,
    )
    trainer = GRPOTrainer(config=config, db_root=data_root() / "dev_databases")

    start = time.time()
    result = trainer.fit(train_tasks)
    elapsed = time.time() - start
    metrics = result["metrics"]

    results_path = results_root() / "training_results.json"
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
            "Reward: first epoch %.4f, last epoch %.4f; last accuracy %.2f%%",
            metrics["reward_mean"][0], metrics["reward_mean"][-1], 100 * metrics["accuracy"][-1],
        )
    logger.info("Results: %s", results_path)
    logger.info("Checkpoints: %s", result["checkpoint_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
