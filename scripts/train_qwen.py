#!/usr/bin/env python3
"""Train Qwen model on BIRD using GRPO with execution-based rewards.

Usage:
    python scripts/train_qwen.py --questions 100 --epochs 3
    python scripts/train_qwen.py --questions 50 --epochs 1  # Quick test
    python scripts/train_qwen.py --questions 300 --epochs 3  # Full training
"""

import argparse
import logging
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.config import data_root
from verdict.data.loaders import load_bird_dev
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    
    # Training parameters
    parser.add_argument("--questions", type=int, default=100, help="Number of BIRD questions to train on")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct", help="Model name")
    parser.add_argument("--checkpoint-dir", default="checkpoints", help="Checkpoint directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    # Generation parameters
    parser.add_argument("--n-generations", type=int, default=8, help="Number of SQL attempts per question")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    
    args = parser.parse_args()
    
    # Set random seed
    import random
    import torch
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    
    logger.info("=" * 60)
    logger.info("QWEN TRAINING WITH GRPO")
    logger.info("=" * 60)
    logger.info(f"Model: {args.model}")
    logger.info(f"Questions: {args.questions}")
    logger.info(f"Epochs: {args.epochs}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Generations per question: {args.n_generations}")
    logger.info(f"Temperature: {args.temperature}")
    logger.info(f"Checkpoint dir: {args.checkpoint_dir}")
    logger.info(f"Random seed: {args.seed}")
    logger.info("=" * 60)
    
    # Check GPU
    import torch
    if torch.cuda.is_available():
        logger.info(f"✅ GPU available: {torch.cuda.get_device_name(0)}")
        logger.info(f"   CUDA version: {torch.version.cuda}")
        logger.info(f"   GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.warning("⚠️  No GPU detected! Training will be VERY slow on CPU.")
        response = input("Continue anyway? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Exiting.")
            return
    
    # Load BIRD data
    logger.info("\nLoading BIRD dataset...")
    try:
        all_tasks = load_bird_dev()
        logger.info(f"✅ Loaded {len(all_tasks)} BIRD dev questions")
    except Exception as e:
        logger.error(f"❌ Failed to load BIRD dataset: {e}")
        logger.error("Make sure BIRD dataset is in datasets/ folder")
        return
    
    # Select subset
    import random
    random.seed(args.seed)
    if args.questions < len(all_tasks):
        # Select balanced by difficulty
        simple = [t for t in all_tasks if t.difficulty == "simple"]
        moderate = [t for t in all_tasks if t.difficulty == "moderate"]
        challenging = [t for t in all_tasks if t.difficulty == "challenging"]
        
        n_simple = int(args.questions * len(simple) / len(all_tasks))
        n_moderate = int(args.questions * len(moderate) / len(all_tasks))
        n_challenging = args.questions - n_simple - n_moderate
        
        train_tasks = (
            random.sample(simple, min(n_simple, len(simple))) +
            random.sample(moderate, min(n_moderate, len(moderate))) +
            random.sample(challenging, min(n_challenging, len(challenging)))
        )
        logger.info(f"Selected {len(train_tasks)} questions:")
        logger.info(f"  Simple: {sum(1 for t in train_tasks if t.difficulty == 'simple')}")
        logger.info(f"  Moderate: {sum(1 for t in train_tasks if t.difficulty == 'moderate')}")
        logger.info(f"  Challenging: {sum(1 for t in train_tasks if t.difficulty == 'challenging')}")
    else:
        train_tasks = all_tasks
    
    # Initialize trainer
    logger.info("\nInitializing trainer...")
    config = GRPOTrainingConfig(
        model_name=args.model,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        num_generations=args.n_generations,
        temperature=args.temperature,
        checkpoint_dir=Path(args.checkpoint_dir),
    )
    
    try:
        trainer = GRPOTrainer(config, db_root=data_root())
        logger.info("✅ Trainer initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize trainer: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Train
    logger.info("\n" + "=" * 60)
    logger.info("STARTING TRAINING")
    logger.info("=" * 60)
    logger.info("This will take 2-3 hours for 100 questions")
    logger.info("Progress will be printed after each epoch")
    logger.info("Checkpoints saved after each epoch")
    logger.info("You can stop anytime with Ctrl+C and resume later")
    logger.info("=" * 60 + "\n")
    
    try:
        result = trainer.fit(train_tasks)
        
        logger.info("\n" + "=" * 60)
        logger.info("TRAINING COMPLETE!")
        logger.info("=" * 60)
        logger.info(f"Checkpoints saved to: {result['checkpoint_dir']}")
        logger.info(f"Metrics: {result['metrics']}")
        logger.info("\nFinal metrics:")
        logger.info(f"  Reward mean: {result['metrics']['reward_mean']}")
        logger.info(f"  Reward std:  {result['metrics']['reward_std']}")
        logger.info(f"  Accuracy:    {result['metrics']['accuracy']}")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n\nTraining interrupted by user")
        logger.info(f"Checkpoints saved to: {args.checkpoint_dir}")
        logger.info("You can resume training from the last checkpoint")
    except Exception as e:
        logger.error(f"\n\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
