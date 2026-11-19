"""Supervised fine-tuning (SFT): learn to write the gold SQL.

    trainer = SFTTrainer(SFTConfig(...), db_root=..., schemas_file=...)
    trainer.fit(train_tasks, val_tasks)

For each question the model sees the same prompt GRPO uses (schema, question,
hint) followed by the gold answer, ```sql <gold SQL> ``` and the end token.
The loss is the cross-entropy of the answer tokens only: the model is taught
to write the answer, not to repeat the prompt.

Why SFT before GRPO: GRPO learns only from groups where some answers are
better than others. On Phase 1 most groups were all wrong, so most questions
taught nothing. SFT gives the model the basics (output format, quoting
column names, choosing tables, using the hint) so that GRPO has something to
work with.

Kaggle stops a session after 12 hours. ``time_limit_hours`` makes the run
save and stop cleanly before that; ``fit(..., resume_from=...)`` continues
from the saved step with the same data order.
"""

from __future__ import annotations

import json
import logging
import math
import random
import shutil
import statistics
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path

import torch

from verdict.data.loaders import BirdTask
from verdict.train.data_prep import SchemaStore, render_prompt, sql_answer
from verdict.train.evaluation import evaluate_tasks
from verdict.train.modeling import (
    amp_dtype,
    needs_grad_scaler,
    LoraSettings,
    adapter_base_model,
    completion_token_logprobs,
    count_parameters,
    is_adapter_dir,
    load_for_training,
    load_tokenizer,
    trainable_parameters,
)
from verdict.train.reward import SQLRewardFunction

logger = logging.getLogger(__name__)


@dataclass
class SFTConfig:
    model_name: str = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

    num_epochs: int = 1
    batch_size: int = 16  # examples per optimizer step
    micro_batch_size: int = 2  # examples per forward/backward; lower it if out of memory
    learning_rate: float = 1e-4  # usual for LoRA; full fine-tuning needs about 1e-5
    warmup_steps: int = 20
    weight_decay: float = 0.0
    max_grad_norm: float = 1.0
    seed: int = 42
    max_steps: int | None = None  # stop after this many optimizer steps (for short tests)

    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05

    gradient_checkpointing: bool = True
    amp: bool = True

    # Prompt: identical to GRPO, so the model is trained on what it will see.
    max_schema_chars: int = 6000
    schema_sample_rows: int = 2
    include_evidence: bool = True
    max_answer_tokens: int = 256  # longer gold answers are skipped (GRPO generates at most 256)
    max_total_tokens: int = 4096  # prompt + answer; longer examples are skipped

    eval_max_tasks: int | None = 200
    eval_before_training: bool = True
    eval_every_steps: int | None = None  # also evaluate every N steps (None: only after each epoch)

    log_every_steps: int = 10
    save_every_steps: int = 100
    time_limit_hours: float | None = None

    checkpoint_dir: Path = Path("checkpoints/sft")
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")
    reward_timeout_s: float = 5.0
    reward_workers: int = 8


def _log(msg: str) -> None:
    print(msg, flush=True)
    logger.debug(msg)


class SFTTrainer:
    """Teach a model to write the gold SQL for each question."""

    def __init__(self, config: SFTConfig, db_root: Path | str | None = None,
                 schemas_file: Path | str | None = None, init_from: Path | str | None = None):
        """``db_root`` holds ``<db_id>/<db_id>.sqlite`` (needed to evaluate);
        ``schemas_file`` supplies schemas for databases that are not there.
        ``init_from`` loads a saved adapter instead of starting a new one."""
        self.config = config
        self.device = torch.device(config.device)
        self.db_root = Path(db_root) if db_root else None
        self.checkpoint_dir = Path(config.checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        random.seed(config.seed)
        torch.manual_seed(config.seed)

        source = adapter_base_model(init_from) if init_from else config.model_name
        _log(f"Loading model: {source}" + (f" with adapter {init_from}" if init_from else ""))
        self.tokenizer = self._load_tokenizer(source)
        self.model = self._load_model(init_from or source)
        trainable, total = count_parameters(self.model)
        _log(f"Trainable parameters: {trainable:,} of {total:,} ({100 * trainable / total:.2f}%)")

        self.use_amp = config.amp and self.device.type == "cuda"
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.use_amp and needs_grad_scaler())
        self.optimizer = torch.optim.AdamW(
            trainable_parameters(self.model), lr=config.learning_rate, weight_decay=config.weight_decay
        )
        self.scheduler = None  # built in fit(), once the number of steps is known

        self.schemas = SchemaStore(self.db_root, schemas_file, config.schema_sample_rows, config.max_schema_chars)
        self.reward_fn = (
            SQLRewardFunction(self.db_root, timeout_s=config.reward_timeout_s, workers=config.reward_workers)
            if self.db_root else None
        )
        self.eos_id = self.tokenizer.eos_token_id
        self._prompts: dict[int, str] = {}
        self.global_step = 0
        self.best_val_accuracy = -1.0
        self._last_ran = 0.0
        self.metrics: dict[str, list] = {"loss": [], "val_accuracy": [], "val_ran": [], "val_step": []}

    # ------------------------------------------------------------------ loading

    def _load_model(self, source: str | Path):
        c = self.config
        return load_for_training(
            source, self.device, LoraSettings(r=c.lora_r, alpha=c.lora_alpha, dropout=c.lora_dropout),
            gradient_checkpointing=c.gradient_checkpointing,
        )

    @staticmethod
    def _load_tokenizer(source: str | Path):
        return load_tokenizer(source)

    # ------------------------------------------------------------------ data

    def prompt_for(self, task: BirdTask) -> str:
        if task.question_id not in self._prompts:
            self._prompts[task.question_id] = render_prompt(
                self.tokenizer, task, self.schemas(task.db_id), self.config.include_evidence
            )
        return self._prompts[task.question_id]

    def encode(self, task: BirdTask) -> tuple[list[int], list[int]]:
        """``(prompt_ids, answer_ids)``; the answer ends with the end-of-turn token."""
        prompt = self.tokenizer(self.prompt_for(task), add_special_tokens=False)["input_ids"]
        answer = self.tokenizer(sql_answer(task.gold_sql), add_special_tokens=False)["input_ids"]
        return prompt, answer + [self.eos_id]

    def _examples(self, tasks: list[BirdTask]) -> list[tuple[int, list[int], list[int]]]:
        c = self.config
        out, no_schema, too_long = [], 0, 0
        for t in tasks:
            try:
                prompt, answer = self.encode(t)
            except FileNotFoundError:
                no_schema += 1
                continue
            if len(answer) > c.max_answer_tokens or len(prompt) + len(answer) > c.max_total_tokens:
                too_long += 1
                continue
            out.append((t.question_id, prompt, answer))
        _log(f"Training examples: {len(out)} (skipped {no_schema} without a schema, {too_long} too long)")
        return out

    # ----------------------------------------------------------------- training

    def _autocast(self):
        return torch.autocast("cuda", dtype=amp_dtype()) if self.use_amp else nullcontext()

    def _schedule(self, total_steps: int):
        warmup = max(self.config.warmup_steps, 1)

        def factor(step: int) -> float:
            # Linear warm-up, then linear decay to zero at the last step.
            if step < warmup:
                return (step + 1) / warmup
            return max(0.0, (total_steps - step) / max(total_steps - warmup, 1))

        return torch.optim.lr_scheduler.LambdaLR(self.optimizer, factor)

    def _step_batches(self, examples: list, epoch: int) -> list[list]:
        """This epoch's batches. The order depends only on the seed and epoch,
        so a resumed run sees the same batches as the original."""
        order = list(examples)
        random.Random(self.config.seed + epoch).shuffle(order)
        bs = self.config.batch_size
        return [order[i : i + bs] for i in range(0, len(order), bs)]

    def train_step(self, batch: list[tuple[int, list[int], list[int]]]) -> float:
        """One optimizer step on ``batch``. Returns the mean loss per answer token."""
        self.model.train()
        n_tokens = sum(len(a) for _, _, a in batch)
        mb = self.config.micro_batch_size
        total = 0.0
        for i in range(0, len(batch), mb):
            chunk = batch[i : i + mb]
            token_logp, _ = completion_token_logprobs(
                self.model, [(p, a) for _, p, a in chunk], self.tokenizer.pad_token_id,
                self.device, self._autocast(),
            )
            loss = -token_logp.sum() / n_tokens
            self.scaler.scale(loss).backward()
            total += loss.item()

        self.scaler.unscale_(self.optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(trainable_parameters(self.model), self.config.max_grad_norm)
        if torch.isfinite(grad_norm):
            self.scaler.step(self.optimizer)
        else:
            logger.warning("non-finite gradient norm; skipping step %d", self.global_step)
        self.scaler.update()
        self.optimizer.zero_grad(set_to_none=True)
        if self.scheduler is not None:
            self.scheduler.step()
        self.global_step += 1
        return total

    def fit(self, train_tasks: list[BirdTask], val_tasks: list[BirdTask] | None = None,
            resume_from: Path | str | None = None) -> dict:
        """Train for ``num_epochs`` (or ``max_steps``), evaluating on ``val_tasks``.

        Saves ``latest/`` every ``save_every_steps`` and at the end, and
        ``best/`` when validation accuracy improves. Returns a summary dict;
        ``finished`` is False if the time limit stopped the run early.
        """
        c = self.config
        start_time = time.time()
        examples = self._examples(train_tasks)
        if not examples:
            raise ValueError("no usable training examples")
        val_tasks = self._evaluable(val_tasks or [])

        steps_per_epoch = math.ceil(len(examples) / c.batch_size)
        total_steps = steps_per_epoch * c.num_epochs
        if c.max_steps:
            total_steps = min(total_steps, c.max_steps)
        self.scheduler = self._schedule(total_steps)

        if resume_from:
            self._restore(Path(resume_from))
            _log(f"Resumed at step {self.global_step}/{total_steps}")

        _log(
            f"\nSFT: {len(examples)} examples, {c.num_epochs} epoch(s), {total_steps} steps of "
            f"{c.batch_size} examples, learning rate {c.learning_rate}, validation: {len(val_tasks)} tasks"
        )
        if self.device.type == "cuda":
            props = torch.cuda.get_device_properties(self.device)
            _log(f"GPU: {props.name} ({props.total_memory / 1e9:.1f} GB)")

        val_before = None
        if val_tasks and c.eval_before_training and self.global_step == 0:
            val_before = self.evaluate(val_tasks)

        finished = True
        window: list[float] = []
        t_window = time.time()
        for epoch in range(c.num_epochs):
            batches = self._step_batches(examples, epoch)
            for b, batch in enumerate(batches):
                step = epoch * steps_per_epoch + b
                if step < self.global_step:
                    continue  # already done before the resume
                if self.global_step >= total_steps:
                    break

                window.append(self.train_step(batch))
                s = self.global_step
                if s % c.log_every_steps == 0 or s == total_steps:
                    per_step = (time.time() - t_window) / len(window)
                    loss = statistics.fmean(window)
                    self.metrics["loss"].append([s, loss])
                    _log(
                        f"[step {s}/{total_steps} epoch {epoch + 1}] loss {loss:.4f} | "
                        f"lr {self.scheduler.get_last_lr()[0]:.2e} | {per_step:.1f}s/step, "
                        f"about {per_step * (total_steps - s) / 60:.0f} min left"
                    )
                    window, t_window = [], time.time()
                if c.eval_every_steps and s % c.eval_every_steps == 0 and val_tasks:
                    self._evaluate_and_keep_best(val_tasks)
                if s % c.save_every_steps == 0:
                    self._save("latest")
                if c.time_limit_hours and time.time() - start_time > c.time_limit_hours * 3600:
                    _log(f"Time limit reached at step {s}/{total_steps}; saving to resume later.")
                    finished = False
                    break
            if not finished or self.global_step >= total_steps:
                break
            if val_tasks:
                self._evaluate_and_keep_best(val_tasks)

        if finished and val_tasks and (not self.metrics["val_step"] or self.metrics["val_step"][-1] != self.global_step):
            self._evaluate_and_keep_best(val_tasks)
        self._save("latest")
        return {
            "finished": finished,
            "global_step": self.global_step,
            "total_steps": total_steps,
            "val_accuracy_before": val_before,
            "best_val_accuracy": self.best_val_accuracy if val_tasks else None,
            "metrics": self.metrics,
            "checkpoint_dir": str(self.checkpoint_dir),
        }

    # --------------------------------------------------------------- evaluation

    def _evaluable(self, tasks: list[BirdTask]) -> list[BirdTask]:
        if not tasks:
            return []
        if self.db_root is None:
            _log("No database folder given; validation is skipped.")
            return []
        ok = [t for t in tasks if (self.db_root / t.db_id / f"{t.db_id}.sqlite").exists()]
        return ok[: self.config.eval_max_tasks or None]

    def evaluate(self, tasks: list[BirdTask]) -> float:
        result = evaluate_tasks(
            self.model, self.tokenizer, [self.prompt_for(t) for t in tasks], tasks, self.reward_fn,
            max_tokens=self.config.max_answer_tokens, amp=self.use_amp, log=_log,
        )
        _log(
            f"  evaluated {len(tasks)} val tasks in {result.seconds:.0f}s: "
            f"{100 * result.accuracy:.1f}% correct, {100 * result.ran_rate:.1f}% ran"
        )
        if result.failure_counts():
            _log(f"  failed because: {result.failure_summary()}")
        self._last_ran = result.ran_rate
        return result.accuracy

    def _evaluate_and_keep_best(self, val_tasks: list[BirdTask]) -> None:
        acc = self.evaluate(val_tasks)
        self.metrics["val_accuracy"].append(acc)
        self.metrics["val_ran"].append(self._last_ran)
        self.metrics["val_step"].append(self.global_step)
        if acc > self.best_val_accuracy:
            self.best_val_accuracy = acc
            self._save("best")

    # -------------------------------------------------------------- checkpoints

    def _save(self, name: str) -> None:
        """Write ``<checkpoint_dir>/<name>/`` atomically (temp folder, then rename).

        With LoRA the optimizer, scheduler and scaler state are saved too
        (they are small), so a resumed run continues exactly. For full
        fine-tuning they would be several GB and are not saved.
        """
        path = self.checkpoint_dir / name
        tmp = self.checkpoint_dir / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        self.model.save_pretrained(tmp)
        self.tokenizer.save_pretrained(tmp)
        if is_adapter_dir(tmp):
            torch.save(
                {
                    "optimizer": self.optimizer.state_dict(),
                    "scheduler": self.scheduler.state_dict() if self.scheduler else None,
                    "scaler": self.scaler.state_dict(),
                },
                tmp / "trainer_state.pt",
            )
        (tmp / "sft_config.json").write_text(json.dumps(asdict(self.config), indent=2, default=str))
        (tmp / "sft_state.json").write_text(json.dumps(
            {"global_step": self.global_step, "best_val_accuracy": self.best_val_accuracy,
             "metrics": self.metrics}, indent=2,
        ))
        shutil.rmtree(path, ignore_errors=True)
        tmp.rename(path)
        _log(f"Saved checkpoint: {path} (step {self.global_step})")

    def _restore(self, path: Path) -> None:
        """Load step counters and optimizer state from a checkpoint folder.

        The adapter weights themselves must already be loaded: create the
        trainer with ``init_from=path``.
        """
        state = json.loads((path / "sft_state.json").read_text())
        self.global_step = state["global_step"]
        self.best_val_accuracy = state.get("best_val_accuracy", -1.0)
        self.metrics = state.get("metrics", self.metrics)
        extra = path / "trainer_state.pt"
        if extra.exists():
            saved = torch.load(extra, map_location=self.device, weights_only=False)
            self.optimizer.load_state_dict(saved["optimizer"])
            if saved["scheduler"] and self.scheduler is not None:
                self.scheduler.load_state_dict(saved["scheduler"])
            self.scaler.load_state_dict(saved["scaler"])
        else:
            # Without saved state the schedule is moved to the right step and
            # the optimizer starts fresh.
            for _ in range(self.global_step):
                self.scheduler.step()
