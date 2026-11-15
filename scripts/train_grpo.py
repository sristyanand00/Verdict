#!/usr/bin/env python
"""Train a text-to-SQL model with GRPO.

Two data sources:

  BIRD dev (Phase 1 practice; a model trained on dev cannot be scored on dev):
    python scripts/train_grpo.py --num-tasks 300 --epochs 2

  BIRD train (Phase 2), usually with LoRA and starting from the SFT adapter:
    python scripts/train_grpo.py --train-dir /path/to/bird_train \\
        --init-adapter /path/to/sft/best --lora-r 16 --task-ids kept_ids.json

--train-dir is the folder made when BIRD train was prepared on Kaggle:
train_all.json, schemas.json and train_databases/. Validation questions are
held out with the same seed as scripts/train_sft.py, so GRPO never trains on
the questions SFT was checked on.

Environment:
    VERDICT_DATA_ROOT     folder holding dev.json and dev_databases/ (dev mode)
    VERDICT_RESULTS_ROOT  where training_results.json is written (default: results/)
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
from verdict.data.loaders import has_database, load_bird_dev, load_bird_train  # noqa: E402
from verdict.train.batch import (  # noqa: E402
    create_train_val_split,
    holdout_split,
    stratified_train_val_split,
)
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
DEFAULTS = GRPOTrainingConfig()
LORA_LR = 1e-5


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train text-to-SQL model with GRPO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--model", default=DEFAULTS.model_name, help="Hugging Face model name")
    p.add_argument("--epochs", type=int, default=DEFAULTS.num_epochs)
    p.add_argument("--batch-size", type=int, default=DEFAULTS.batch_size, help="questions per batch")
    p.add_argument("--lr", type=float, default=None,
                   help=f"learning rate (default {DEFAULTS.learning_rate} full fine-tuning, {LORA_LR} LoRA)")
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
    p.add_argument("--seed", type=int, default=DEFAULTS.seed)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")

    dev = p.add_argument_group("BIRD dev mode")
    dev.add_argument("--train-ratio", type=float, default=0.8)
    dev.add_argument("--no-stratified", action="store_true", help="split without preserving difficulty mix")

    train = p.add_argument_group("BIRD train mode")
    train.add_argument("--train-dir", type=Path, default=None,
                       help="folder with train_all.json, schemas.json and train_databases/")
    train.add_argument("--val-size", type=int, default=200, help="questions held out for validation")
    train.add_argument("--split-seed", type=int, default=0, help="must match the SFT run")
    train.add_argument("--task-ids", type=Path, default=None,
                       help="JSON list of question ids to train on (from scripts/pass_rate.py)")

    lora = p.add_argument_group("LoRA")
    lora.add_argument("--lora-r", type=int, default=DEFAULTS.lora_r, help="0 trains every weight")
    lora.add_argument("--lora-alpha", type=int, default=DEFAULTS.lora_alpha)
    lora.add_argument("--init-adapter", type=Path, default=None, help="start from this saved adapter (e.g. SFT best/)")
    return p.parse_args()


def load_tasks(args):
    """(all_tasks, train_tasks, val_tasks, db_root)."""
    if args.train_dir is None:
        all_tasks = load_bird_dev(data_root=data_root())
        if args.num_tasks:
            # BIRD dev is sorted by database, so the first N would all be one or two
            # databases. Take every k-th task instead to keep the variety.
            step = max(len(all_tasks) // args.num_tasks, 1)
            all_tasks = all_tasks[::step][: args.num_tasks]
        split = create_train_val_split if args.no_stratified else stratified_train_val_split
        train_tasks, val_tasks = split(all_tasks, args.train_ratio)
        return all_tasks, train_tasks, val_tasks, data_root() / "dev_databases"

    all_tasks = load_bird_train(args.train_dir / "train_all.json", args.train_dir / "train_databases")
    train_tasks, val_tasks = holdout_split(all_tasks, args.val_size, seed=args.split_seed, eligible=has_database)
    train_tasks = [t for t in train_tasks if has_database(t)]
    if args.task_ids:
        keep = set(json.loads(args.task_ids.read_text()))
        train_tasks = [t for t in train_tasks if t.question_id in keep]
    if args.num_tasks and args.num_tasks < len(train_tasks):
        step = len(train_tasks) // args.num_tasks
        train_tasks = train_tasks[::step][: args.num_tasks]
    return all_tasks, train_tasks, val_tasks, args.train_dir / "train_databases"


def main() -> int:
    args = parse_args()

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU (this will be very slow)")
        args.device = "cpu"

    try:
        all_tasks, train_tasks, val_tasks, db_root = load_tasks(args)
    except FileNotFoundError as e:
        logger.error("Failed to load BIRD: %s", e)
        logger.error("Dev mode: set VERDICT_DATA_ROOT. Train mode: check --train-dir.")
        return 1
    distribution = dict(Counter(t.difficulty for t in train_tasks))
    logger.info("Loaded %d tasks; train %d %s, val %d", len(all_tasks), len(train_tasks), distribution, len(val_tasks))

    use_lora = args.lora_r > 0 or args.init_adapter is not None
    lr = args.lr if args.lr is not None else (LORA_LR if use_lora else DEFAULTS.learning_rate)
    config = GRPOTrainingConfig(
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=lr,
        num_generations=args.num_generations,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        micro_batch_size=args.micro_batch_size,
        eval_max_tasks=args.eval_max_tasks,
        seed=args.seed,
        checkpoint_dir=Path(args.checkpoint_dir),
        device=args.device,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        init_adapter=args.init_adapter,
        schemas_file=args.train_dir / "schemas.json" if args.train_dir else None,
    )
    trainer = GRPOTrainer(config=config, db_root=db_root)

    start = time.time()
    result = trainer.fit(train_tasks, val_tasks)
    elapsed = time.time() - start
    metrics = result["metrics"]

    results_path = results_root() / "training_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                "learning_rate": lr,
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
