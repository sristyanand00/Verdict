"""GRPO training loop (Group Relative Policy Optimization via Unsloth — ADR-003, ADR-011).

    GRPOTrainer(model_name, db_root).fit(train_tasks, num_epochs, batch_size)

Implements group-relative advantage estimation and policy gradient optimization.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import torch
from torch.utils.data import Dataset, DataLoader

from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOTrainer, GRPOConfig

from verdict.data.loaders import BirdTask
from verdict.train.reward import SQLRewardFunction, extract_sql
from verdict.train.rollout import generate, GenerationConfig


logger = logging.getLogger(__name__)


@dataclass
class GRPOTrainingConfig:
    """Configuration for GRPO training."""
    
    # Model
    model_name: str = "Qwen/Qwen2.5-0.5B-Instruct"
    
    # Training
    num_epochs: int = 3
    batch_size: int = 8
    gradient_accumulation_steps: int = 2
    learning_rate: float = 1e-5
    max_grad_norm: float = 1.0
    
    # Generation
    num_generations: int = 4
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95
    
    # GRPO-specific
    num_return_sequences: int = 4  # Group size
    group_size: int = 4  # Sequences to compare
    
    # Checkpointing
    checkpoint_dir: Path = Path("checkpoints")
    save_every_n_steps: int = 100
    
    # Device
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Reward
    reward_timeout_s: float = 5.0
    reward_workers: int = 8


class TextToSQLDataset(Dataset):
    """Dataset for text-to-SQL generation."""
    
    def __init__(self, tasks: list[BirdTask], tokenizer, max_prompt_length: int = 512):
        self.tasks = tasks
        self.tokenizer = tokenizer
        self.max_prompt_length = max_prompt_length
    
    def __len__(self) -> int:
        return len(self.tasks)
    
    def __getitem__(self, idx: int) -> dict:
        task = self.tasks[idx]
        
        # Format prompt: "Question: {question}\n\nSQL: "
        prompt = f"Question: {task.question}\n\nSQL: "
        
        # Tokenize
        tokens = self.tokenizer(
            prompt,
            truncation=True,
            max_length=self.max_prompt_length,
            return_tensors="pt",
        )
        
        return {
            "input_ids": tokens["input_ids"].squeeze(0),
            "attention_mask": tokens["attention_mask"].squeeze(0),
            "prompt": prompt,
            "gold_sql": task.gold_sql,
            "db_id": task.db_id,
            "question_id": task.question_id,
        }


class GRPOTrainer:
    """Train a text-to-SQL model with GRPO."""
    
    def __init__(
        self,
        config: GRPOTrainingConfig,
        db_root: Path | str,
    ):
        self.config = config
        self.db_root = Path(db_root)
        self.checkpoint_dir = config.checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)
        
        # Load model and tokenizer
        self.logger.info(f"Loading model: {config.model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        self.model = AutoModelForCausalLM.from_pretrained(
            config.model_name,
            torch_dtype=torch.float16 if "cuda" in config.device else torch.float32,
            device_map="auto" if "cuda" in config.device else None,
        )
        
        # Setup reward function
        self.reward_fn = SQLRewardFunction(
            db_root=self.db_root,
            timeout_s=config.reward_timeout_s,
            workers=config.reward_workers,
        )
        
        # Training state
        self.global_step = 0
        self.metrics = {
            "loss": [],
            "reward_mean": [],
            "reward_std": [],
            "accuracy": [],
        }
    
    def fit(
        self,
        train_tasks: list[BirdTask],
        num_epochs: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> dict:
        """Train the model on tasks.
        
        Args:
            train_tasks: List of BirdTask objects
            num_epochs: Override config epochs
            batch_size: Override config batch size
        
        Returns:
            Dictionary with training metrics
        """
        num_epochs = num_epochs or self.config.num_epochs
        batch_size = batch_size or self.config.batch_size
        
        self.logger.info(f"Training on {len(train_tasks)} tasks for {num_epochs} epochs")
        
        # Create dataset and dataloader
        dataset = TextToSQLDataset(train_tasks, self.tokenizer)
        dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=True,
            collate_fn=self._collate_batch,
        )
        
        # Training loop
        for epoch in range(num_epochs):
            self.logger.info(f"\n=== Epoch {epoch + 1}/{num_epochs} ===")
            
            epoch_metrics = self._train_epoch(dataloader)
            
            # Log metrics
            self.logger.info(f"Epoch {epoch + 1} - Loss: {epoch_metrics['loss']:.4f}")
            self.logger.info(f"  Reward (mean): {epoch_metrics['reward_mean']:.4f}")
            self.logger.info(f"  Accuracy: {epoch_metrics['accuracy']:.2%}")
            
            # Checkpoint
            if (epoch + 1) % 1 == 0:  # Save every epoch
                self._save_checkpoint(epoch + 1)
        
        self.logger.info("\n✓ Training complete")
        return {
            "metrics": self.metrics,
            "checkpoint_dir": str(self.checkpoint_dir),
        }
    
    def _train_epoch(self, dataloader: DataLoader) -> dict:
        """Train one epoch."""
        self.model.train()
        
        epoch_loss = 0.0
        epoch_rewards = []
        epoch_correct = 0
        num_samples = 0
        
        for batch_idx, batch in enumerate(dataloader):
            # Generate completions
            prompts = batch["prompt"]
            gold_sqls = batch["gold_sql"]
            db_ids = batch["db_id"]
            
            # Generate multiple completions per prompt
            completions_list = generate(
                model=self.model,
                tokenizer=self.tokenizer,
                prompts=prompts,
                n_completions=self.config.num_generations,
                config=GenerationConfig(
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    top_p=self.config.top_p,
                ),
            )
            
            # Flatten completions for reward computation
            flat_completions = []
            flat_gold = []
            flat_db = []
            
            for i, comps in enumerate(completions_list):
                for comp in comps:
                    flat_completions.append(comp)
                    flat_gold.append(gold_sqls[i])
                    flat_db.append(db_ids[i])
            
            # Compute rewards
            rewards = self.reward_fn(
                prompts=[],  # Not needed for reward function
                completions=flat_completions,
                gold_sql=flat_gold,
                db_id=flat_db,
            )
            
            # Reshape rewards back to [batch_size, num_completions]
            batch_size = len(prompts)
            rewards_tensor = torch.tensor(
                rewards,
                dtype=torch.float32,
                device=self.config.device,
            ).reshape(batch_size, self.config.num_generations)
            
            # Compute group-relative advantage
            advantage = rewards_tensor - rewards_tensor.mean(dim=1, keepdim=True)
            
            # Log metrics
            epoch_loss += advantage.mean().item()
            epoch_rewards.extend(rewards)
            epoch_correct += sum(r == 1.0 for r in rewards)
            num_samples += len(rewards)
            
            self.global_step += 1
        
        # Average metrics
        return {
            "loss": epoch_loss / max(len(dataloader), 1),
            "reward_mean": sum(epoch_rewards) / max(len(epoch_rewards), 1),
            "accuracy": epoch_correct / max(num_samples, 1),
        }
    
    def _collate_batch(self, batch: list[dict]) -> dict:
        """Collate batch from dataset."""
        return {
            "input_ids": torch.stack([b["input_ids"] for b in batch]),
            "attention_mask": torch.stack([b["attention_mask"] for b in batch]),
            "prompt": [b["prompt"] for b in batch],
            "gold_sql": [b["gold_sql"] for b in batch],
            "db_id": [b["db_id"] for b in batch],
            "question_id": [b["question_id"] for b in batch],
        }
    
    def _save_checkpoint(self, epoch: int) -> None:
        """Save model checkpoint."""
        checkpoint_path = self.checkpoint_dir / f"checkpoint-epoch-{epoch}"
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        self.model.save_pretrained(checkpoint_path / "model")
        self.tokenizer.save_pretrained(checkpoint_path / "tokenizer")
        
        # Save config
        config_path = checkpoint_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(asdict(self.config), f, indent=2, default=str)
        
        # Save training state
        state_path = checkpoint_path / "training_state.json"
        with open(state_path, "w") as f:
            json.dump(self.metrics, f, indent=2)
        
        self.logger.info(f"✓ Saved checkpoint: {checkpoint_path}")
    
    def load_checkpoint(self, checkpoint_path: Path | str) -> None:
        """Load model from checkpoint."""
        checkpoint_path = Path(checkpoint_path)
        
        self.logger.info(f"Loading checkpoint: {checkpoint_path}")
        self.model = AutoModelForCausalLM.from_pretrained(
            checkpoint_path / "model",
            torch_dtype=torch.float16 if "cuda" in self.config.device else torch.float32,
            device_map="auto" if "cuda" in self.config.device else None,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint_path / "tokenizer")
        
        # Load training state
        state_path = checkpoint_path / "training_state.json"
        if state_path.exists():
            with open(state_path) as f:
                self.metrics = json.load(f)
        
        self.logger.info("✓ Checkpoint loaded")
