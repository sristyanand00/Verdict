"""Sample several completions per prompt from a Hugging Face causal LM.

    generate(model, tokenizer, prompts, n_completions) -> list[list[str]]
    generate_ids(model, tokenizer, prompts, n_completions) -> list[Rollout]

``generate_ids`` also returns the exact token ids that were sampled. The GRPO
loop scores those ids directly; decoding to text and re-tokenizing can give a
different token sequence, so the gradient would be computed for tokens the
model never produced.
"""

from contextlib import nullcontext
from dataclasses import dataclass, field

import torch

from verdict.train.grpo_utils import trim_completion


@dataclass
class GenerationConfig:
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 0.95
    top_k: int = 50
    repetition_penalty: float = 1.0

    def to_dict(self) -> dict:
        """Keyword arguments for ``model.generate``."""
        kwargs = {
            "max_new_tokens": self.max_tokens,
            "repetition_penalty": self.repetition_penalty,
            "do_sample": self.temperature > 0,
        }
        if self.temperature > 0:
            kwargs.update(temperature=self.temperature, top_p=self.top_p, top_k=self.top_k)
        else:
            # Greedy. Passing sampling arguments here makes transformers warn.
            kwargs.update(temperature=None, top_p=None, top_k=None)
        return kwargs


@dataclass
class Rollout:
    """One prompt and its sampled completions."""

    prompt_ids: list[int]
    completion_ids: list[list[int]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)


def eos_token_ids(model, tokenizer) -> set[int]:
    """Every token id that ends generation (chat models often have several)."""
    ids: set[int] = set()
    gen_eos = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    for value in (gen_eos, tokenizer.eos_token_id):
        if isinstance(value, int):
            ids.add(value)
        elif value:
            ids.update(value)
    return ids


def _autocast(model, enabled: bool):
    device_type = next(model.parameters()).device.type
    if enabled and device_type == "cuda":
        return torch.autocast("cuda", dtype=torch.float16)
    return nullcontext()


def generate_ids(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    amp: bool = True,
) -> list[Rollout]:
    """Sample ``n_completions`` per prompt; return token ids and decoded text.

    Prompts are never truncated. A truncated prompt silently loses its end,
    which is where the question is. Keep prompts short at the source instead
    (see ``max_schema_chars`` in the GRPO config).
    """
    config = config or GenerationConfig()
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    gen_kwargs = {
        **config.to_dict(),
        "num_return_sequences": n_completions,
        "pad_token_id": pad_id,
        "use_cache": True,
    }
    eos = eos_token_ids(model, tokenizer)
    device = next(model.parameters()).device

    was_training = model.training
    model.eval()
    rollouts = []
    try:
        with torch.no_grad(), _autocast(model, amp):
            for prompt in prompts:
                inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(device)
                prompt_len = inputs["input_ids"].shape[1]
                output_ids = model.generate(**inputs, **gen_kwargs)
                rollout = Rollout(prompt_ids=inputs["input_ids"][0].tolist())
                for seq in output_ids:
                    ids = trim_completion(seq[prompt_len:].tolist(), eos, pad_id)
                    rollout.completion_ids.append(ids)
                    rollout.texts.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
                rollouts.append(rollout)
    finally:
        if was_training:
            model.train()
    return rollouts


def generate(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    amp: bool = True,
) -> list[list[str]]:
    """Return ``n_completions`` sampled completion texts for each prompt."""
    return [r.texts for r in generate_ids(model, tokenizer, prompts, n_completions, config, amp)]
