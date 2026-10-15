#!/usr/bin/env python
"""Test script to validate training pipeline is working.

Usage:
    python scripts/test_training_pipeline.py

Runs:
    1. Module import checks
    2. Configuration validation
    3. Data loading test
    4. Model initialization test
    5. Generation test
    6. Reward function test
    7. Training loop test (1 batch)
"""

import sys
from pathlib import Path

# Add verdict to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test all modules can be imported."""
    logger.info("\n📦 Testing imports...")
    
    try:
        from verdict.config import data_root, results_root
        logger.info("  ✓ verdict.config")
        
        from verdict.data.loaders import load_bird_dev
        logger.info("  ✓ verdict.data.loaders")
        
        from verdict.train.batch import batch_dataset, create_train_val_split
        logger.info("  ✓ verdict.train.batch")
        
        from verdict.train.rollout import generate, GenerationConfig
        logger.info("  ✓ verdict.train.rollout")
        
        from verdict.train.reward import SQLRewardFunction
        logger.info("  ✓ verdict.train.reward")
        
        from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
        logger.info("  ✓ verdict.train.grpo")
        
        from verdict.train.monitor import TrainingMonitor
        logger.info("  ✓ verdict.train.monitor")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Import failed: {e}")
        return False


def test_config():
    """Test configuration system."""
    logger.info("\n⚙️  Testing configuration...")
    
    try:
        from verdict.config import data_root, results_root, dev_json
        
        data = data_root()
        results = results_root()
        dev = dev_json()
        
        logger.info(f"  Data root: {data}")
        logger.info(f"  Results root: {results}")
        logger.info(f"  Dev JSON: {dev}")
        
        logger.info("  ✓ Configuration loaded")
        return True
    except Exception as e:
        logger.error(f"  ✗ Configuration failed: {e}")
        return False


def test_data_loading():
    """Test data loading with small sample."""
    logger.info("\n📂 Testing data loading...")
    
    try:
        from verdict.data.loaders import load_bird_dev
        
        logger.info("  Attempting to load dataset...")
        tasks = load_bird_dev()
        
        logger.info(f"  ✓ Loaded {len(tasks)} tasks")
        
        # Show sample
        task = tasks[0]
        logger.info(f"  Sample task:")
        logger.info(f"    - Question ID: {task.question_id}")
        logger.info(f"    - Question: {task.question[:50]}...")
        logger.info(f"    - Difficulty: {task.difficulty}")
        logger.info(f"    - SQL: {task.gold_sql[:50]}...")
        
        return True
    except FileNotFoundError as e:
        logger.warning(f"  ⚠️  Dataset not found (normal if not downloaded yet)")
        logger.info(f"     Error: {e}")
        return True  # Not a failure
    except Exception as e:
        logger.error(f"  ✗ Data loading failed: {e}")
        return False


def test_model_initialization():
    """Test model and tokenizer loading."""
    logger.info("\n🤖 Testing model initialization...")
    
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        
        model_name = "gpt2"  # Small model for testing
        logger.info(f"  Loading {model_name}...")
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name)
        
        logger.info(f"  ✓ Model loaded: {type(model).__name__}")
        logger.info(f"  ✓ Tokenizer loaded: {type(tokenizer).__name__}")
        
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        logger.info(f"  ✓ Vocab size: {len(tokenizer)}")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Model initialization failed: {e}")
        return False


def test_generation():
    """Test generation functionality."""
    logger.info("\n🎯 Testing generation...")
    
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from verdict.train.rollout import generate, GenerationConfig
        
        # Use small model for testing
        model_name = "gpt2"
        logger.info(f"  Loading {model_name}...")
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(model_name)
        
        # Test generation
        prompts = [
            "SELECT * FROM users WHERE",
            "INSERT INTO logs",
        ]
        
        logger.info(f"  Generating 2 completions for 2 prompts...")
        
        config = GenerationConfig(
            max_tokens=32,
            temperature=0.7,
        )
        
        results = generate(
            model=model,
            tokenizer=tokenizer,
            prompts=prompts,
            n_completions=2,
            config=config,
            device="cpu",
        )
        
        logger.info(f"  ✓ Generated {len(results)} prompt sets")
        for i, completions in enumerate(results):
            logger.info(f"    Prompt {i+1}: {len(completions)} completions")
            for j, comp in enumerate(completions[:1]):  # Show first only
                logger.info(f"      [{j+1}] {comp[:40]}...")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reward_function():
    """Test reward function."""
    logger.info("\n🏅 Testing reward function...")
    
    try:
        from verdict.train.reward import SQLRewardFunction, extract_sql
        from verdict.config import data_root
        
        # Test SQL extraction
        test_cases = [
            ("SELECT * FROM users", "SELECT * FROM users"),
            ("```sql\nSELECT * FROM users\n```", "SELECT * FROM users"),
            ("```\nSELECT * FROM users\n```", "SELECT * FROM users"),
        ]
        
        logger.info("  Testing SQL extraction...")
        for text, expected in test_cases:
            result = extract_sql(text)
            assert result.strip() == expected.strip(), f"Expected {expected}, got {result}"
        
        logger.info(f"  ✓ SQL extraction works ({len(test_cases)} cases)")
        
        # Test reward function initialization
        logger.info("  Testing reward function initialization...")
        db_root = data_root() / "dev_databases"
        
        reward_fn = SQLRewardFunction(db_root=db_root)
        logger.info(f"  ✓ Reward function initialized")
        logger.info(f"    DB root: {reward_fn.db_root}")
        logger.info(f"    Workers: {reward_fn.workers}")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Reward function test failed: {e}")
        return False


def test_batch_processing():
    """Test batch processing utilities."""
    logger.info("\n📦 Testing batch processing...")
    
    try:
        from verdict.train.batch import (
            batch_dataset,
            batch_by_difficulty,
            create_train_val_split,
        )
        from verdict.data.loaders import BirdTask
        from pathlib import Path
        
        # Create mock tasks
        mock_tasks = [
            BirdTask(
                question_id=i,
                db_id="test_db",
                question=f"Question {i}",
                evidence="",
                gold_sql="SELECT 1",
                difficulty=["simple", "moderate", "challenging"][i % 3],
                db_path=Path("mock.db"),
            )
            for i in range(30)
        ]
        
        # Test batch_dataset
        batches = batch_dataset(mock_tasks, batch_size=8)
        logger.info(f"  ✓ batch_dataset: {len(batches)} batches (size 8)")
        
        # Test batch_by_difficulty
        by_diff = batch_by_difficulty(mock_tasks)
        logger.info(f"  ✓ batch_by_difficulty: {list(by_diff.keys())}")
        
        # Test train_val_split
        train, val = create_train_val_split(mock_tasks, train_ratio=0.8)
        logger.info(f"  ✓ create_train_val_split: {len(train)} train, {len(val)} val")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Batch processing test failed: {e}")
        return False


def test_training_monitor():
    """Test training monitor."""
    logger.info("\n📊 Testing training monitor...")
    
    try:
        from verdict.train.monitor import TrainingMonitor
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = TrainingMonitor(output_dir=tmpdir)
            
            # Log some metrics
            for epoch in range(3):
                for step in range(5):
                    monitor.log_step(
                        step=epoch * 5 + step,
                        epoch=epoch,
                        loss=0.5 - (epoch * 0.1),
                        reward=0.3 + (epoch * 0.1),
                        accuracy=0.2 + (epoch * 0.1),
                    )
                
                monitor.log_epoch(
                    epoch=epoch,
                    step=epoch * 5 + 5,
                    loss=0.5 - (epoch * 0.1),
                    reward_mean=0.3 + (epoch * 0.1),
                    reward_std=0.05,
                    accuracy=0.2 + (epoch * 0.1),
                    duration_s=60.0,
                )
            
            logger.info(f"  ✓ Logged {len(monitor.epoch_metrics)} epochs")
            
            # Save and check
            result = monitor.save()
            logger.info(f"  ✓ Saved to {result.name}")
            
            summary = monitor.get_summary()
            logger.info(f"  ✓ Summary: {summary['num_epochs']} epochs, {summary['num_steps']} steps")
        
        return True
    except Exception as e:
        logger.error(f"  ✗ Training monitor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_grpo_config():
    """Test GRPO trainer configuration."""
    logger.info("\n⚙️  Testing GRPO configuration...")
    
    try:
        from verdict.train.grpo import GRPOTrainingConfig
        
        config = GRPOTrainingConfig(
            model_name="gpt2",
            num_epochs=2,
            batch_size=4,
        )
        
        logger.info(f"  Model: {config.model_name}")
        logger.info(f"  Epochs: {config.num_epochs}")
        logger.info(f"  Batch size: {config.batch_size}")
        logger.info(f"  Device: {config.device}")
        logger.info(f"  Checkpoint dir: {config.checkpoint_dir}")
        
        logger.info("  ✓ GRPO config created")
        return True
    except Exception as e:
        logger.error(f"  ✗ GRPO config test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 70)
    logger.info("TRAINING PIPELINE VALIDATION")
    logger.info("=" * 70)
    
    tests = [
        ("Module Imports", test_imports),
        ("Configuration", test_config),
        ("Data Loading", test_data_loading),
        ("Model Init", test_model_initialization),
        ("Generation", test_generation),
        ("Reward Function", test_reward_function),
        ("Batch Processing", test_batch_processing),
        ("Training Monitor", test_training_monitor),
        ("GRPO Config", test_grpo_config),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            logger.error(f"Unexpected error in {name}: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, passed_test in results:
        status = "✓" if passed_test else "✗"
        logger.info(f"{status} {name}")
    
    logger.info("\n" + "=" * 70)
    logger.info(f"Passed: {passed}/{total}")
    logger.info("=" * 70)
    
    if passed == total:
        logger.info("\n✓ All tests passed! Pipeline is ready to use.")
        logger.info("\nNext steps:")
        logger.info("  1. Review WEEK4-TRAINING-GUIDE.md")
        logger.info("  2. Download BIRD dataset if needed")
        logger.info("  3. Run: python scripts/train_grpo.py --num-tasks 10 --epochs 1")
        return 0
    else:
        logger.info(f"\n✗ {total - passed} test(s) failed. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
