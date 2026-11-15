#!/usr/bin/env python
"""Supervised fine-tuning on BIRD train: teach the model to write the gold SQL.

Usage (Kaggle, T4):
    python scripts/train_sft.py --train-dir /path/to/bird_train \\
        --checkpoint-dir /kaggle/working/sft --time-limit-hours 11

    # quick check that everything runs (a few minutes)
    python scripts/train_sft.py --train-dir ... --max-steps 20 --val-size 20

    # continue a run that stopped at the time limit
    python scripts/train_sft.py --train-dir ... --resume /path/to/sft/latest

--train-dir is the folder made when BIRD train was prepared on Kaggle:
train_all.json (every question), schemas.json (every database's schema) and
train_databases/ (the databases that were kept). Every question is used for
training, including those whose database was dropped, because training only
needs the schema text. Validation questions need their database, because
their answers are run and checked.

Environment:
    VERDICT_RESULTS_ROOT  where sft_results.json is written (default: results/)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import results_root  # noqa: E402
from verdict.data.loaders import has_database, load_bird_train  # noqa: E402
from verdict.train.batch import holdout_split  # noqa: E402
from verdict.train.sft import SFTConfig, SFTTrainer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
DEFAULTS = SFTConfig()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Supervised fine-tuning on BIRD train",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--train-dir", type=Path, required=True,
                   help="folder with train_all.json, schemas.json and train_databases/")
    p.add_argument("--model", default=DEFAULTS.model_name)
    p.add_argument("--epochs", type=int, default=DEFAULTS.num_epochs)
    p.add_argument("--batch-size", type=int, default=DEFAULTS.batch_size, help="examples per optimizer step")
    p.add_argument("--micro-batch-size", type=int, default=DEFAULTS.micro_batch_size,
                   help="examples per forward/backward; lower it if you run out of GPU memory")
    p.add_argument("--lr", type=float, default=DEFAULTS.learning_rate)
    p.add_argument("--lora-r", type=int, default=DEFAULTS.lora_r, help="0 trains every weight")
    p.add_argument("--lora-alpha", type=int, default=DEFAULTS.lora_alpha)
    p.add_argument("--max-steps", type=int, default=None, help="stop after N optimizer steps")
    p.add_argument("--num-tasks", type=int, default=None, help="train on only N questions")
    p.add_argument("--val-size", type=int, default=200, help="questions held out for validation")
    p.add_argument("--split-seed", type=int, default=0, help="GRPO must use the same value")
    p.add_argument("--eval-every", type=int, default=None, help="also validate every N steps")
    p.add_argument("--no-eval-before", action="store_true", help="skip validating the untrained model")
    p.add_argument("--save-every", type=int, default=DEFAULTS.save_every_steps)
    p.add_argument("--time-limit-hours", type=float, default=None,
                   help="save and stop after this long (Kaggle stops sessions at 12 h)")
    p.add_argument("--checkpoint-dir", default="checkpoints/sft")
    p.add_argument("--resume", type=Path, default=None, help="checkpoint folder to continue from")
    p.add_argument("--seed", type=int, default=DEFAULTS.seed)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        logger.warning("CUDA not available, falling back to CPU (this will be very slow)")
        args.device = "cpu"

    for name in ("train_all.json", "schemas.json", "train_databases"):
        if not (args.train_dir / name).exists():
            logger.error("%s not found in %s", name, args.train_dir)
            return 1

    tasks = load_bird_train(args.train_dir / "train_all.json", args.train_dir / "train_databases")
    train_tasks, val_tasks = holdout_split(tasks, args.val_size, seed=args.split_seed, eligible=has_database)
    if args.num_tasks and args.num_tasks < len(train_tasks):
        step = len(train_tasks) // args.num_tasks
        train_tasks = train_tasks[::step][: args.num_tasks]
    logger.info(
        "BIRD train: %d questions; training on %d, validating on %d (%d databases on disk)",
        len(tasks), len(train_tasks), len(val_tasks),
        len({t.db_id for t in tasks if has_database(t)}),
    )

    config = SFTConfig(
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        micro_batch_size=args.micro_batch_size,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        max_steps=args.max_steps,
        eval_max_tasks=args.val_size,
        eval_before_training=not args.no_eval_before,
        eval_every_steps=args.eval_every,
        save_every_steps=args.save_every,
        time_limit_hours=args.time_limit_hours,
        checkpoint_dir=Path(args.checkpoint_dir),
        seed=args.seed,
        device=args.device,
    )
    trainer = SFTTrainer(
        config,
        db_root=args.train_dir / "train_databases",
        schemas_file=args.train_dir / "schemas.json",
        init_from=args.resume,
    )

    start = time.time()
    result = trainer.fit(train_tasks, val_tasks, resume_from=args.resume)
    elapsed = time.time() - start

    results_path = results_root() / "sft_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(
        {
            "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            "data": {"questions": len(tasks), "train": len(train_tasks), "val": len(val_tasks)},
            "training": {"duration_s": elapsed, **result},
        },
        indent=2,
    ))

    logger.info("SFT %s in %.1f minutes (step %d of %d)",
                "finished" if result["finished"] else "stopped at the time limit",
                elapsed / 60, result["global_step"], result["total_steps"])
    if not result["finished"]:
        logger.info("Continue with: --resume %s", Path(result["checkpoint_dir"]) / "latest")
    if result["val_accuracy_before"] is not None:
        logger.info("Validation accuracy before training: %.1f%%", 100 * result["val_accuracy_before"])
    if result["best_val_accuracy"] is not None:
        logger.info("Best validation accuracy: %.1f%%", 100 * result["best_val_accuracy"])
    logger.info("Results: %s", results_path)
    logger.info("Checkpoints: %s (latest/ and best/)", result["checkpoint_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
