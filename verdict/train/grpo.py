"""GRPO training loop (ADR-003, ADR-011).

    trainer = GRPOTrainer(config, db_root=<folder holding <db_id>/<db_id>.sqlite>)
    trainer.fit(train_tasks, val_tasks)

One step:
  1. Build a chat prompt per question: schema + question + BIRD hint.
  2. Sample ``num_generations`` SQL completions per prompt (the GRPO group).
  3. Score each by executing it against the database (``SQLRewardFunction``).
  4. Advantage = reward - group mean.
  5. Policy gradient on the exact sampled tokens: loss = -advantage * log p.

There is one gradient update per batch of samples, so the policy that sampled
is the policy being updated; the PPO ratio is 1 and clipping would be a no-op.
There is no KL penalty against a reference model: it would need a second copy
of the model in GPU memory, and Dr. GRPO / DAPO report it is not needed for
verifiable-reward tasks at this scale.

Precision: trained weights and optimizer state are float32; forward passes
run in half-precision autocast (``modeling.amp_dtype``): bfloat16 on GPUs
that support it (RTX 30xx and newer), float16 with a GradScaler otherwise.
Kaggle's T4 and P100 have no native bfloat16, and training float16 weights
directly with AdamW produces NaNs (its epsilon, 1e-8, rounds to zero in
float16).

LoRA: with ``lora_r > 0`` only small adapter matrices are trained and the
frozen base weights are kept in half precision (see ``verdict.train.modeling``). This
is what fits a 1.5B model on a T4. ``init_adapter`` starts from an existing
adapter, such as the result of supervised fine-tuning.
"""

import json
import logging
import random
import shutil
import sqlite3
import statistics
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM

from verdict.data.loaders import BirdTask
from verdict.train.data_prep import SchemaStore, render_prompt
from verdict.train.evaluation import evaluate_tasks
from verdict.train.grpo_utils import group_advantages, repeat_per_group
from verdict.train.modeling import (
    amp_dtype,
    needs_grad_scaler,
    LoraSettings,
    adapter_base_model,
    completion_token_logprobs,
    count_parameters,
    is_adapter_dir,
    load_tokenizer,
    prepare_for_training,
    trainable_parameters,
)
from verdict.train.reward import SQLRewardFunction
from verdict.train.rollout import GenerationConfig, generate_ids

logger = logging.getLogger(__name__)


@dataclass
class GRPOTrainingConfig:
    model_name: str = "Qwen/Qwen2.5-0.5B-Instruct"

    num_epochs: int = 3
    batch_size: int = 4  # questions per batch; each yields num_generations completions
    gradient_accumulation_steps: int = 1  # batches per optimizer step
    learning_rate: float = 1e-6  # TRL's GRPO default for full fine-tuning; LoRA needs about 1e-5
    weight_decay: float = 0.0
    max_grad_norm: float = 1.0
    seed: int = 42

    # Generation; num_generations is the GRPO group size.
    num_generations: int = 8
    max_tokens: int = 256
    temperature: float = 0.9  # GRPO needs varied completions within a group
    top_p: float = 0.95

    # Advantage = reward - group mean; divide by group std too if True.
    scale_rewards: bool = False

    # Memory. micro_batch_size completions go through each forward/backward.
    micro_batch_size: int = 4
    gradient_checkpointing: bool = True
    amp: bool = True  # half-precision autocast on CUDA (bf16 or fp16, see amp_dtype)

    # Prompt. BIRD schemas can be very long; the schema is shortened (fewer
    # sample rows, then cut) to fit, rather than truncating the prompt, which
    # would cut off the question at its end.
    max_schema_chars: int = 6000
    schema_sample_rows: int = 2
    include_evidence: bool = True
    # Saved schemas for databases that are not on disk (BIRD train preparation).
    schemas_file: Path | None = None

    # LoRA. 0 trains every weight. init_adapter continues from a saved adapter
    # (for example the SFT result); its base model replaces model_name.
    lora_r: int = 0
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    init_adapter: Path | None = None

    # Validation: greedy accuracy on up to this many val tasks per epoch.
    eval_max_tasks: int | None = 100
    eval_before_training: bool = True

    checkpoint_dir: Path = Path("checkpoints")
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")

    reward_scheme: str = "sparse"
    reward_timeout_s: float = 5.0
    reward_workers: int = 8


def _log(msg: str) -> None:
    """Print for notebooks (flushed so Kaggle shows it live) and log for files."""
    print(msg, flush=True)
    logger.debug(msg)


class GRPOTrainer:
    """Train a text-to-SQL model with GRPO."""

    def __init__(self, config: GRPOTrainingConfig, db_root: Path | str):
        self.config = config
        self.device = torch.device(config.device)
        self.db_root = Path(db_root)
        if not self.db_root.is_dir():
            raise FileNotFoundError(
                f"db_root not found: {self.db_root}\n"
                "db_root must be the dev_databases folder itself, the one holding "
                "<db_id>/<db_id>.sqlite, e.g. data_root() / 'dev_databases'."
            )
        self.checkpoint_dir = Path(config.checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        random.seed(config.seed)
        torch.manual_seed(config.seed)

        source = config.model_name
        if config.init_adapter is not None:
            source = adapter_base_model(config.init_adapter)
            _log(f"Starting from adapter {config.init_adapter} (base model {source})")
        _log(f"Loading model: {source}")
        self.tokenizer = self._load_tokenizer(source)
        self.model = self._load_model(source, adapter_path=config.init_adapter)
        trainable, total = count_parameters(self.model)
        _log(f"Trainable parameters: {trainable:,} of {total:,} ({100 * trainable / total:.2f}%)")

        self.use_amp = config.amp and self.device.type == "cuda"
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.use_amp and needs_grad_scaler())
        self.optimizer = self._new_optimizer()

        self.reward_fn = SQLRewardFunction(
            db_root=self.db_root,
            timeout_s=config.reward_timeout_s,
            workers=config.reward_workers,
            scheme=config.reward_scheme,
        )
        self.schemas = SchemaStore(
            self.db_root, config.schemas_file, config.schema_sample_rows, config.max_schema_chars
        )
        self._prompts: dict[int, str] = {}
        self._micro_steps = 0  # batches whose gradients are accumulated but not yet applied
        self._has_grads = False
        self.global_step = 0
        self.best_val_accuracy = -1.0
        self.metrics: dict[str, list[float]] = {
            "reward_mean": [], "reward_std": [], "accuracy": [], "loss": [], "val_accuracy": [],
        }

    # ------------------------------------------------------------------ loading

    def _lora(self) -> LoraSettings:
        c = self.config
        return LoraSettings(r=c.lora_r, alpha=c.lora_alpha, dropout=c.lora_dropout)

    def _load_model(self, source: str | Path, adapter_path: str | Path | None = None):
        # Loaded without a dtype argument and cast afterwards: the keyword is
        # `torch_dtype` in older transformers and `dtype` in newer ones.
        model = AutoModelForCausalLM.from_pretrained(source)
        return prepare_for_training(
            model, self.device, self._lora(), adapter_path=adapter_path,
            gradient_checkpointing=self.config.gradient_checkpointing,
        )

    @staticmethod
    def _load_tokenizer(source: str | Path):
        return load_tokenizer(source)

    def _new_optimizer(self):
        return torch.optim.AdamW(
            trainable_parameters(self.model), lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

    # ------------------------------------------------------------------ prompts

    def prompt_for(self, task: BirdTask) -> str:
        """The exact text fed to the model for ``task``."""
        if task.question_id not in self._prompts:
            self._prompts[task.question_id] = render_prompt(
                self.tokenizer, task, self.schemas(task.db_id), self.config.include_evidence
            )
        return self._prompts[task.question_id]

    def _usable(self, tasks: list[BirdTask]) -> list[BirdTask]:
        """Drop tasks whose database cannot be read, with a warning.

        GRPO runs every answer, so the database itself is required, not only
        its schema.
        """
        ok, skipped = [], 0
        for t in tasks:
            if not (self.db_root / t.db_id / f"{t.db_id}.sqlite").exists():
                skipped += 1
                continue
            try:
                self.prompt_for(t)
            except (FileNotFoundError, sqlite3.Error) as e:
                logger.warning("skipping question %s: %s", t.question_id, e)
                continue
            ok.append(t)
        if skipped:
            _log(f"Skipped {skipped} questions whose database is not in {self.db_root}")
        return ok

    # ----------------------------------------------------------------- training

    def fit(
        self,
        train_tasks: list[BirdTask],
        val_tasks: list[BirdTask] | None = None,
        num_epochs: int | None = None,
        batch_size: int | None = None,
    ) -> dict:
        """Train, evaluating on ``val_tasks`` (if given) before and after each epoch.

        Returns ``{"metrics", "checkpoint_dir", "best_val_accuracy", "val_accuracy_before"}``.
        Checkpoints: ``latest/`` every epoch and ``best/`` when validation improves.
        """
        num_epochs = num_epochs or self.config.num_epochs
        batch_size = batch_size or self.config.batch_size
        train_tasks = self._usable(train_tasks)
        val_tasks = self._usable(val_tasks or [])[: self.config.eval_max_tasks or None]
        if not train_tasks:
            raise ValueError("no usable training tasks (check db_root and the dataset)")

        _log(
            f"\nTraining: {len(train_tasks)} tasks, {num_epochs} epochs, batch {batch_size} x "
            f"{self.config.num_generations} completions, validation: {len(val_tasks)} tasks"
        )
        if self.device.type == "cuda":
            props = torch.cuda.get_device_properties(self.device)
            _log(f"GPU: {props.name} ({props.total_memory / 1e9:.1f} GB)")

        val_before = None
        if val_tasks and self.config.eval_before_training:
            val_before = self.evaluate(val_tasks)
            _log(f"Validation accuracy before training: {100 * val_before:.1f}%")

        rng = random.Random(self.config.seed)
        for epoch in range(1, num_epochs + 1):
            _log(f"\n{'=' * 70}\nEPOCH {epoch}/{num_epochs}\n{'=' * 70}")
            epoch_start = time.time()
            order = list(train_tasks)
            rng.shuffle(order)
            batches = [order[i : i + batch_size] for i in range(0, len(order), batch_size)]

            rewards, losses = [], []
            for b, tasks in enumerate(batches, 1):
                r, loss = self._train_batch(tasks, epoch, num_epochs, b, len(batches))
                rewards.extend(r)
                losses.append(loss)
            self._optimizer_step()  # flush any partial accumulation

            mean = statistics.fmean(rewards) if rewards else 0.0
            std = statistics.pstdev(rewards) if rewards else 0.0
            accuracy = sum(r == self.reward_fn.rewards["correct"] for r in rewards) / max(len(rewards), 1)
            self.metrics["reward_mean"].append(mean)
            self.metrics["reward_std"].append(std)
            self.metrics["accuracy"].append(accuracy)
            self.metrics["loss"].append(statistics.fmean(losses) if losses else 0.0)

            summary = (
                f"Epoch {epoch} done in {time.time() - epoch_start:.0f}s | "
                f"reward {mean:.4f} +/- {std:.4f} | train accuracy {100 * accuracy:.1f}%"
            )
            improved = False
            if val_tasks:
                val_acc = self.evaluate(val_tasks)
                self.metrics["val_accuracy"].append(val_acc)
                summary += f" | val accuracy {100 * val_acc:.1f}%"
                if val_acc > self.best_val_accuracy:
                    self.best_val_accuracy = val_acc
                    improved = True
            _log(f"\n{summary}")

            self._save_checkpoint("latest", epoch)
            if improved:
                self._save_checkpoint("best", epoch)

        return {
            "metrics": self.metrics,
            "checkpoint_dir": str(self.checkpoint_dir),
            "best_val_accuracy": self.best_val_accuracy if val_tasks else None,
            "val_accuracy_before": val_before,
        }

    def _train_batch(
        self, tasks: list[BirdTask], epoch: int, num_epochs: int, b: int, num_batches: int
    ) -> tuple[list[float], float]:
        n = self.config.num_generations
        t0 = time.time()
        prompts = [self.prompt_for(t) for t in tasks]

        rollouts = generate_ids(
            self.model, self.tokenizer, prompts, n_completions=n, amp=self.use_amp,
            config=GenerationConfig(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
            ),
        )
        t_gen = time.time() - t0

        # Every list below is in the same order: n completions of task 0, then task 1, ...
        completions = [text for r in rollouts for text in r.texts]
        rewards = self.reward_fn(
            prompts=repeat_per_group(prompts, n),
            completions=completions,
            gold_sql=repeat_per_group([t.gold_sql for t in tasks], n),
            db_id=repeat_per_group([t.db_id for t in tasks], n),
        )
        t_reward = time.time() - t0 - t_gen

        advantages = group_advantages(rewards, n, scale=self.config.scale_rewards)
        samples = [
            (r.prompt_ids, ids, adv)
            for r, ids, adv in zip(
                repeat_per_group(rollouts, n),
                [ids for r in rollouts for ids in r.completion_ids],
                advantages,
            )
        ]
        loss = self._accumulate_gradients(samples)
        self._micro_steps += 1
        if self._micro_steps >= self.config.gradient_accumulation_steps:
            self._optimizer_step()

        correct = sum(r == self.reward_fn.rewards["correct"] for r in rewards)
        ran = sum(r != self.reward_fn.rewards["failed"] for r in rewards)
        _log(
            f"[epoch {epoch}/{num_epochs} batch {b}/{num_batches}] "
            f"correct {correct}/{len(rewards)}, ran {ran}/{len(rewards)}, "
            f"loss {loss:+.4f} | gen {t_gen:.0f}s, sql {t_reward:.0f}s, "
            f"update {time.time() - t0 - t_gen - t_reward:.0f}s"
        )
        return rewards, loss

    def _autocast(self):
        return torch.autocast("cuda", dtype=amp_dtype()) if self.use_amp else nullcontext()

    def _accumulate_gradients(self, samples: list[tuple[list[int], list[int], float]]) -> float:
        """Backpropagate -advantage * log p(completion) over ``samples``.

        Runs ``micro_batch_size`` completions at a time and calls backward on
        each chunk, so only one chunk's activations are in memory at once.
        Completions with zero advantage contribute nothing and are skipped;
        a group whose completions all scored the same is skipped entirely.

        The loss is divided by ``max_tokens`` rather than each completion's own
        length (Dr. GRPO), so long wrong answers are not penalised less per
        token than short ones.
        """
        denom = len(samples) * self.config.max_tokens * self.config.gradient_accumulation_steps
        active = [s for s in samples if s[2] != 0.0 and s[1]]
        total = 0.0
        self.model.train()
        mb = self.config.micro_batch_size
        for i in range(0, len(active), mb):
            chunk = active[i : i + mb]
            logp = self._sequence_logprobs(chunk)
            adv = torch.tensor([s[2] for s in chunk], dtype=torch.float32, device=self.device)
            loss = -(adv * logp).sum() / denom
            self.scaler.scale(loss).backward()
            self._has_grads = True
            total += loss.item()
        return total

    def _sequence_logprobs(self, chunk: list[tuple[list[int], list[int], float]]) -> torch.Tensor:
        """Summed log-probability of each completion's tokens given its prompt."""
        token_logp, rows = completion_token_logprobs(
            self.model, [(p, c) for p, c, _ in chunk], self.tokenizer.pad_token_id,
            self.device, self._autocast(),
        )
        return torch.zeros(len(chunk), device=self.device).index_add(0, rows, token_logp)

    def _optimizer_step(self) -> None:
        self._micro_steps = 0
        if not self._has_grads:
            self.optimizer.zero_grad(set_to_none=True)
            return
        self._has_grads = False
        self.scaler.unscale_(self.optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(trainable_parameters(self.model), self.config.max_grad_norm)
        if torch.isfinite(grad_norm):
            self.scaler.step(self.optimizer)
            self.global_step += 1
        else:
            logger.warning("non-finite gradient norm (%s); skipping this update", grad_norm.item())
        self.scaler.update()
        self.optimizer.zero_grad(set_to_none=True)

    # --------------------------------------------------------------- evaluation

    def evaluate(self, tasks: list[BirdTask]) -> float:
        """Greedy (temperature 0) execution accuracy on ``tasks``."""
        if not tasks:
            return 0.0
        result = evaluate_tasks(
            self.model, self.tokenizer, [self.prompt_for(t) for t in tasks], tasks, self.reward_fn,
            max_tokens=self.config.max_tokens, amp=self.use_amp,
        )
        _log(
            f"  evaluated {len(tasks)} val tasks in {result.seconds:.0f}s: "
            f"{100 * result.accuracy:.1f}% correct, {100 * result.ran_rate:.1f}% ran"
        )
        if result.failure_counts():
            _log(f"  failed because: {result.failure_summary()}")
        return result.accuracy

    # -------------------------------------------------------------- checkpoints

    def _save_checkpoint(self, name: str, epoch: int) -> None:
        """Save to ``<checkpoint_dir>/<name>/``, replacing the previous one.

        Only ``latest`` and ``best`` are kept: each is ~2 GB for a 0.5B model
        and Kaggle's /kaggle/working is limited to 20 GB. With LoRA only the
        adapter is saved (tens of MB).
        """
        path = self.checkpoint_dir / name
        tmp = self.checkpoint_dir / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        self.model.save_pretrained(tmp)
        self.tokenizer.save_pretrained(tmp)
        (tmp / "training_config.json").write_text(json.dumps(asdict(self.config), indent=2, default=str))
        (tmp / "training_state.json").write_text(
            json.dumps({"epoch": epoch, "global_step": self.global_step, "metrics": self.metrics}, indent=2)
        )
        shutil.rmtree(path, ignore_errors=True)
        tmp.rename(path)
        _log(f"Saved checkpoint: {path} (epoch {epoch})")

    def load_checkpoint(self, checkpoint_path: Path | str) -> None:
        """Load weights saved by ``_save_checkpoint`` (or the older model/ + tokenizer/ layout).

        The optimizer starts fresh; its state is not saved (it would triple
        the checkpoint size).
        """
        path = Path(checkpoint_path)
        model_dir = path / "model" if (path / "model").is_dir() else path
        tok_dir = path / "tokenizer" if (path / "tokenizer").is_dir() else path
        _log(f"Loading checkpoint: {path}")
        if is_adapter_dir(model_dir):
            self.model = self._load_model(adapter_base_model(model_dir), adapter_path=model_dir)
        else:
            self.model = self._load_model(model_dir)
        self.tokenizer = self._load_tokenizer(tok_dir)
        self.optimizer = self._new_optimizer()
        self._prompts.clear()
        state = path / "training_state.json"
        if state.exists():
            data = json.loads(state.read_text())
            self.metrics = data.get("metrics", data)
            self.global_step = data.get("global_step", 0)
