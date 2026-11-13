"""GRPO training loop (ADR-003, ADR-011) - FIXED VERSION

    GRPOTrainer(config, db_root).fit(train_tasks)

Fixed issues:
- Proper policy gradient computation with gradients enabled
- Detailed progress logging with timing information
- Chunked gradient computation for memory efficiency
- Clear batch/epoch progress indicators
"""

import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer

from verdict.data.loaders import BirdTask
from verdict.train.reward import SQLRewardFunction
from verdict.train.rollout import GenerationConfig, generate

logger = logging.getLogger(__name__)


@dataclass
class GRPOTrainingConfig:
    model_name: str = "Qwen/Qwen2.5-0.5B-Instruct"

    num_epochs: int = 3
    batch_size: int = 8
    gradient_accumulation_steps: int = 2
    learning_rate: float = 1e-5
    max_grad_norm: float = 1.0

    # Generation; num_generations is the GRPO group size.
    num_generations: int = 8
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95

    checkpoint_dir: Path = Path("checkpoints")
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")

    reward_timeout_s: float = 5.0
    reward_workers: int = 8


def _prompt(task: BirdTask) -> str:
    return f"Question: {task.question}\n\nSQL: "


class GRPOTrainer:
    """Train a text-to-SQL model with GRPO."""

    def __init__(self, config: GRPOTrainingConfig, db_root: Path | str):
        self.config = config
        self.checkpoint_dir = Path(config.checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Loading model: %s", config.model_name)
        self.tokenizer = self._load_tokenizer(config.model_name)
        self.model = self._load_model(config.model_name)
        
        # Initialize optimizer for policy gradient
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=0.01,
        )
        
        # Enable gradient computation
        self.model.train()
        
        self.reward_fn = SQLRewardFunction(
            db_root=db_root, timeout_s=config.reward_timeout_s, workers=config.reward_workers
        )
        self.global_step = 0
        self.metrics: dict[str, list[float]] = {"reward_mean": [], "reward_std": [], "accuracy": []}

    def _load_model(self, source: str | Path):
        on_gpu = "cuda" in self.config.device
        return AutoModelForCausalLM.from_pretrained(
            source,
            torch_dtype=torch.float16 if on_gpu else torch.float32,
            device_map="auto" if on_gpu else None,
        )

    @staticmethod
    def _load_tokenizer(source: str | Path):
        tokenizer = AutoTokenizer.from_pretrained(source)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        return tokenizer

    def fit(
        self, train_tasks: list[BirdTask], num_epochs: int | None = None, batch_size: int | None = None
    ) -> dict:
        """Run the epochs and return ``{"metrics": ..., "checkpoint_dir": ...}``."""
        num_epochs = num_epochs or self.config.num_epochs
        batch_size = batch_size or self.config.batch_size
        logger.info("Training on %d tasks for %d epochs", len(train_tasks), num_epochs)
        print(f"\n📊 Training: {len(train_tasks)} tasks, {num_epochs} epochs, batch_size={batch_size}")

        # Tasks are batched as-is; the collate function keeps them as a list.
        loader = DataLoader(train_tasks, batch_size=batch_size, shuffle=True, collate_fn=list)
        num_batches = len(loader)

        for epoch in range(1, num_epochs + 1):
            print(f"\n{'='*70}")
            print(f"📅 EPOCH {epoch}/{num_epochs}")
            print(f"{'='*70}")
            epoch_start = time.time()
            
            rewards = self._train_epoch(loader, epoch, num_epochs, num_batches)
            
            mean = statistics.fmean(rewards) if rewards else 0.0
            std = statistics.pstdev(rewards) if rewards else 0.0
            accuracy = sum(r == self.reward_fn.rewards["correct"] for r in rewards) / max(len(rewards), 1)
            self.metrics["reward_mean"].append(mean)
            self.metrics["reward_std"].append(std)
            self.metrics["accuracy"].append(accuracy)
            
            epoch_time = time.time() - epoch_start
            
            print(f"\n{'='*70}")
            print(f"✅ Epoch {epoch} Complete | Time: {epoch_time:.1f}s")
            print(f"   Reward: {mean:.4f} ± {std:.4f} | Accuracy: {100*accuracy:.2f}%")
            print(f"{'='*70}")
            
            logger.info(
                "Epoch %d/%d | reward %.4f +/- %.4f | accuracy %.2f%%",
                epoch, num_epochs, mean, std, 100 * accuracy,
            )
            self._save_checkpoint(epoch)

        return {"metrics": self.metrics, "checkpoint_dir": str(self.checkpoint_dir)}

    def _train_epoch(self, loader: DataLoader, epoch: int, num_epochs: int, num_batches: int) -> list[float]:
        """Sample and score one epoch; returns every completion's reward."""
        gen_config = GenerationConfig(
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            top_p=self.config.top_p,
        )
        n = self.config.num_generations
        epoch_rewards: list[float] = []

        for batch_idx, tasks in enumerate(loader, 1):
            batch_start = time.time()
            print(f"\n[Epoch {epoch}/{num_epochs}] [Batch {batch_idx}/{num_batches}] ({len(tasks)} questions)")
            
            prompts = [_prompt(t) for t in tasks]
            
            # === GENERATION ===
            gen_start = time.time()
            print(f"  🤖 Generating {n} completions per question...")
            
            # Generate WITHOUT gradients (inference mode)
            groups = generate(
                self.model, self.tokenizer, prompts, 
                n_completions=n, config=gen_config,
                return_log_probs=False  # Don't need log probs during generation
            )
            gen_time = time.time() - gen_start
            print(f"  ✅ Generation complete ({gen_time:.1f}s)")
            
            # Flatten for reward calculation
            all_completions = [c for group in groups for c in group]
            all_gold = [t.gold_sql for t in tasks for _ in range(n)]
            all_db_id = [t.db_id for t in tasks for _ in range(n)]
            
            # === SQL EXECUTION & REWARD ===
            reward_start = time.time()
            print(f"  ⚡ Executing {len(all_completions)} SQL queries...")
            
            batch_rewards = self.reward_fn(
                prompts=[],
                completions=all_completions,
                gold_sql=all_gold,
                db_id=all_db_id,
            )
            reward_time = time.time() - reward_start
            epoch_rewards.extend(batch_rewards)
            
            correct_count = sum(r == self.reward_fn.rewards["correct"] for r in batch_rewards)
            batch_acc = correct_count / len(batch_rewards)
            print(f"  ✅ Rewards calculated ({reward_time:.1f}s) | Accuracy: {100*batch_acc:.1f}%")
            
            # === GRPO ADVANTAGE ===
            advantages = []
            for i in range(0, len(batch_rewards), n):
                group_rewards = batch_rewards[i : i + n]
                group_mean = statistics.mean(group_rewards)
                group_advantages = [r - group_mean for r in group_rewards]
                advantages.extend(group_advantages)
            
            # === POLICY GRADIENT UPDATE (FIXED) ===
            update_start = time.time()
            print(f"  🔄 Computing policy gradient...")
            
            # Re-encode prompts for gradient computation
            # We need to compute log probs WITH gradients this time
            self.model.train()
            
            # Process completions in smaller chunks to save memory
            policy_losses = []
            chunk_size = 8  # Process 8 completions at a time
            
            for chunk_start in range(0, len(all_completions), chunk_size):
                chunk_end = min(chunk_start + chunk_size, len(all_completions))
                chunk_prompts = prompts * n  # Repeat prompts for each generation
                chunk_prompts = chunk_prompts[chunk_start:chunk_end]
                chunk_completions = all_completions[chunk_start:chunk_end]
                chunk_advantages = advantages[chunk_start:chunk_end]
                
                # Compute log probabilities for this chunk
                chunk_log_probs = self._compute_log_probs(chunk_prompts, chunk_completions)
                
                # Compute loss for this chunk
                advantages_tensor = torch.tensor(chunk_advantages, dtype=torch.float32, device=self.model.device)
                chunk_loss = -(chunk_log_probs * advantages_tensor).mean()
                policy_losses.append(chunk_loss)
            
            # Average policy loss across all chunks
            policy_loss = torch.stack(policy_losses).mean()
            
            # Backpropagation
            policy_loss.backward()
            
            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
            
            # Update model weights
            self.optimizer.step()
            self.optimizer.zero_grad()
            
            update_time = time.time() - update_start
            print(f"  ✅ Model updated ({update_time:.1f}s) | Loss: {policy_loss.item():.4f}")
            
            batch_time = time.time() - batch_start
            print(f"  ⏱️  Total batch time: {batch_time:.1f}s")
            
            self.global_step += 1

        return epoch_rewards

    def _compute_log_probs(self, prompts: list[str], completions: list[str]) -> torch.Tensor:
        """Compute log probabilities for completions given prompts."""
        log_probs_list = []
        
        for prompt, completion in zip(prompts, completions):
            # Tokenize prompt + completion
            full_text = prompt + completion
            inputs = self.tokenizer(full_text, return_tensors="pt", truncation=True, max_length=512).to(self.model.device)
            prompt_inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(self.model.device)
            
            # Forward pass
            with torch.enable_grad():
                outputs = self.model(**inputs, labels=inputs["input_ids"])
                logits = outputs.logits
            
            # Get log probs for completion tokens only
            prompt_len = prompt_inputs["input_ids"].shape[1]
            completion_logits = logits[0, prompt_len-1:-1, :]  # Shift by 1 for next-token prediction
            completion_ids = inputs["input_ids"][0, prompt_len:]
            
            # Compute log probabilities
            log_probs = torch.log_softmax(completion_logits, dim=-1)
            token_log_probs = log_probs.gather(1, completion_ids.unsqueeze(1)).squeeze(1)
            
            # Sum log probs over sequence
            sequence_log_prob = token_log_probs.sum()
            log_probs_list.append(sequence_log_prob)
        
        return torch.stack(log_probs_list)

    def _save_checkpoint(self, epoch: int) -> None:
        path = self.checkpoint_dir / f"checkpoint-epoch-{epoch}"
        path.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(path / "model")
        self.tokenizer.save_pretrained(path / "tokenizer")
        (path / "config.json").write_text(json.dumps(asdict(self.config), indent=2, default=str))
        (path / "training_state.json").write_text(json.dumps(self.metrics, indent=2))
        logger.info("Saved checkpoint: %s", path)

    def load_checkpoint(self, checkpoint_path: Path | str) -> None:
        path = Path(checkpoint_path)
        logger.info("Loading checkpoint: %s", path)
        self.model = self._load_model(path / "model")
        self.tokenizer = self._load_tokenizer(path / "tokenizer")
        state = path / "training_state.json"
        if state.exists():
            self.metrics = json.loads(state.read_text())
