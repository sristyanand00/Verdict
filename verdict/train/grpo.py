"""GRPO training loop (ADR-003, ADR-011).

    GRPOTrainer(config, db_root).fit(train_tasks)

Current state: each step samples ``num_generations`` completions per prompt
and scores them with SQLRewardFunction, so the reward and accuracy curves are
real. The policy-gradient update is NOT implemented yet: model weights do not
change, and learning_rate / gradient_accumulation_steps / max_grad_norm are
recorded but unused until it is.
"""

import json
import logging
import statistics
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

        # Tasks are batched as-is; the collate function keeps them as a list.
        loader = DataLoader(train_tasks, batch_size=batch_size, shuffle=True, collate_fn=list)

        for epoch in range(1, num_epochs + 1):
            rewards = self._train_epoch(loader)
            mean = statistics.fmean(rewards) if rewards else 0.0
            std = statistics.pstdev(rewards) if rewards else 0.0
            accuracy = sum(r == self.reward_fn.rewards["correct"] for r in rewards) / max(len(rewards), 1)
            self.metrics["reward_mean"].append(mean)
            self.metrics["reward_std"].append(std)
            self.metrics["accuracy"].append(accuracy)
            logger.info(
                "Epoch %d/%d | reward %.4f +/- %.4f | accuracy %.2f%%",
                epoch, num_epochs, mean, std, 100 * accuracy,
            )
            self._save_checkpoint(epoch)

        return {"metrics": self.metrics, "checkpoint_dir": str(self.checkpoint_dir)}

    def _train_epoch(self, loader: DataLoader) -> list[float]:
        """Sample and score one epoch; returns every completion's reward."""
        gen_config = GenerationConfig(
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            top_p=self.config.top_p,
        )
        n = self.config.num_generations
        epoch_rewards: list[float] = []

        for tasks in loader:
            groups = generate(
                self.model, self.tokenizer, [_prompt(t) for t in tasks], n_completions=n, config=gen_config
            )
            epoch_rewards.extend(
                self.reward_fn(
                    prompts=[],
                    completions=[c for group in groups for c in group],
                    gold_sql=[t.gold_sql for t in tasks for _ in range(n)],
                    db_id=[t.db_id for t in tasks for _ in range(n)],
                )
            )
            # TODO: group-relative advantages and the policy-gradient step go here.
            self.global_step += 1

        return epoch_rewards

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
