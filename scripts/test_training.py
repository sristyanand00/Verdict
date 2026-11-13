#!/usr/bin/env python3
"""Quick test: Does training work with 5 questions?

This catches errors BEFORE spending hours on full training.
Should complete in 5-10 minutes on GPU.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from verdict.config import data_root
from verdict.data.loaders import load_bird_dev
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig

def main():
    logger.info("=" * 60)
    logger.info("QUICK TRAINING TEST (5 questions, 1 epoch)")
    logger.info("=" * 60)
    
    # Check GPU
    import torch
    if torch.cuda.is_available():
        logger.info(f"✅ GPU: {torch.cuda.get_device_name(0)}")
    else:
        logger.warning("⚠️  No GPU! Will be slow.")
    
    # Load data
    logger.info("Loading BIRD...")
    tasks = load_bird_dev()[:5]  # Just 5 questions
    logger.info(f"Testing with {len(tasks)} questions")
    
    # Tiny config for quick test
    config = GRPOTrainingConfig(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        num_epochs=1,
        batch_size=2,
        num_generations=4,  # Fewer attempts for speed
        checkpoint_dir=Path("test_checkpoints"),
    )
    
    logger.info("Initializing trainer...")
    trainer = GRPOTrainer(config, db_root=data_root() / "dev_databases")
    
    logger.info("\nStarting quick test...")
    logger.info("Expected time: 5-10 minutes")
    logger.info("-" * 60)
    
    try:
        result = trainer.fit(tasks)
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ TEST PASSED!")
        logger.info("=" * 60)
        logger.info("Training loop works correctly!")
        logger.info(f"Reward mean: {result['metrics']['reward_mean']}")
        logger.info(f"Accuracy: {result['metrics']['accuracy']}")
        logger.info("\n✅ Ready for full training!")
        logger.info("Run: python scripts/train_qwen.py --questions 100 --epochs 3")
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        logger.error("\nFix errors before running full training!")

if __name__ == "__main__":
    main()
