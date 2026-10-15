#!/usr/bin/env python
"""GRPO training script - Week 4 implementation.

Usage:
    python scripts/train_grpo.py [--model MODEL] [--epochs EPOCHS] [--batch-size BS]

Example:
    python scripts/train_grpo.py --model Qwen/Qwen2.5-0.5B-Instruct --epochs 3 --batch-size 8

Environment:
    VERDICT_DATA_ROOT: Path to datasets/ folder (default: datasets)
    CUDA_VISIBLE_DEVICES: GPU device IDs (default: 0)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import torch

# Add verdict package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from verdict.config import data_root, results_root
from verdict.data.loaders import load_bird_dev
from verdict.train.batch import (
    batch_dataset,
    create_train_val_split,
    stratified_train_val_split,
)
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.train.monitor import TrainingMonitor


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main training entrypoint."""
    parser = argparse.ArgumentParser(
        description="Train text-to-SQL model with GRPO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "--model",
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="Model name (HuggingFace hub)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Training batch size",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-5,
        help="Learning rate",
    )
    parser.add_argument(
        "--num-generations",
        type=int,
        default=4,
        help="Number of generations per prompt",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Maximum tokens per generation",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=2,
        help="Gradient accumulation steps",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="checkpoints",
        help="Checkpoint directory",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=None,
        help="Limit number of tasks (useful for testing)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.8,
        help="Train/val split ratio",
    )
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Device (cuda or cpu)",
    )
    parser.add_argument(
        "--no-stratified",
        action="store_true",
        help="Don't use stratified train/val split",
    )
    
    args = parser.parse_args()
    
    # Validate environment
    logger.info("=" * 70)
    logger.info("WEEK 4: GRPO Training Pipeline")
    logger.info("=" * 70)
    
    logger.info(f"\n📋 Configuration:")
    logger.info(f"  Model: {args.model}")
    logger.info(f"  Epochs: {args.epochs}")
    logger.info(f"  Batch size: {args.batch_size}")
    logger.info(f"  Learning rate: {args.lr}")
    logger.info(f"  Generations per prompt: {args.num_generations}")
    logger.info(f"  Max tokens: {args.max_tokens}")
    logger.info(f"  Temperature: {args.temperature}")
    logger.info(f"  Device: {args.device}")
    logger.info(f"  Train ratio: {args.train_ratio}")
    
    # Check CUDA
    if args.device == "cuda":
        if not torch.cuda.is_available():
            logger.warning("⚠️  CUDA not available, falling back to CPU")
            args.device = "cpu"
        else:
            logger.info(f"  GPU: {torch.cuda.get_device_name(0)}")
            logger.info(f"  GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
    
    # Load data
    logger.info(f"\n📂 Loading BIRD dataset...")
    try:
        all_tasks = load_bird_dev(
            dev_json=None,  # Use default
            data_root=data_root(),
            check_db=True,
        )
    except FileNotFoundError as e:
        logger.error(f"❌ Failed to load dataset: {e}")
        logger.info("\nTo download BIRD dataset:")
        logger.info("  1. Visit https://bird-bench.github.io/")
        logger.info("  2. Download dev_databases.zip and dev.json")
        logger.info("  3. Extract to datasets/ folder")
        sys.exit(1)
    
    # Limit tasks if requested
    if args.num_tasks:
        all_tasks = all_tasks[: args.num_tasks]
        logger.info(f"  Limited to {args.num_tasks} tasks (for testing)")
    
    logger.info(f"  ✓ Loaded {len(all_tasks)} tasks")
    
    # Show difficulty distribution
    diff_counts = {}
    for task in all_tasks:
        diff_counts[task.difficulty] = diff_counts.get(task.difficulty, 0) + 1
    
    logger.info(f"  Distribution: {diff_counts}")
    
    # Split train/val
    logger.info(f"\n🔀 Creating train/val split ({args.train_ratio:.0%} train)...")
    if args.no_stratified:
        train_tasks, val_tasks = create_train_val_split(all_tasks, args.train_ratio)
        logger.info("  Using random split")
    else:
        train_tasks, val_tasks = stratified_train_val_split(all_tasks, args.train_ratio)
        logger.info("  Using stratified split (preserves difficulty distribution)")
    
    logger.info(f"  Train: {len(train_tasks)} tasks")
    logger.info(f"  Val: {len(val_tasks)} tasks")
    
    # Create config
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
    
    # Initialize trainer
    logger.info(f"\n🚀 Initializing GRPO trainer...")
    try:
        trainer = GRPOTrainer(
            config=config,
            db_root=data_root() / "dev_databases",
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize trainer: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Initialize monitor
    monitor = TrainingMonitor(output_dir=results_root())
    
    # Train
    logger.info(f"\n⏱️  Starting training...")
    start_time = time.time()
    
    try:
        result = trainer.fit(train_tasks)
        elapsed = time.time() - start_time
        
        logger.info(f"\n✓ Training complete!")
        logger.info(f"  Duration: {elapsed / 60:.1f} minutes")
        logger.info(f"  Checkpoint dir: {result['checkpoint_dir']}")
        
        # Save results
        logger.info(f"\n💾 Saving results...")
        
        results = {
            "config": {
                "model": args.model,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "learning_rate": args.lr,
                "num_generations": args.num_generations,
                "max_tokens": args.max_tokens,
                "temperature": args.temperature,
            },
            "data": {
                "total_tasks": len(all_tasks),
                "train_tasks": len(train_tasks),
                "val_tasks": len(val_tasks),
                "distribution": diff_counts,
            },
            "training": {
                "duration_s": elapsed,
                "checkpoint_dir": result["checkpoint_dir"],
                "metrics": result["metrics"],
            },
        }
        
        # Save to JSON
        results_path = results_root() / "training_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"  ✓ Results: {results_path}")
        
        # Show summary
        logger.info(f"\n📊 Training Summary:")
        logger.info(f"  Initial loss: {result['metrics']['loss'][0]:.4f if result['metrics']['loss'] else 'N/A'}")
        logger.info(f"  Final loss: {result['metrics']['loss'][-1]:.4f if result['metrics']['loss'] else 'N/A'}")
        logger.info(f"  Mean reward: {sum(result['metrics']['reward_mean']) / len(result['metrics']['reward_mean']):.4f if result['metrics']['reward_mean'] else 'N/A'}")
        logger.info(f"  Checkpoint dir: {result['checkpoint_dir']}")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
