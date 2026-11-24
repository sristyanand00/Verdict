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
from verdict.train.modeling import amp_dtype


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
        return torch.autocast("cuda", dtype=amp_dtype())
    return nullcontext()


def generate_ids(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    amp: bool = True,
    batch_size: int = 1,
) -> list[Rollout]:
    """Sample ``n_completions`` per prompt; return token ids and decoded text.

    ``batch_size`` prompts are generated together (left-padded, shortest
    prompts batched together to waste little padding). Results come back in
    the order of ``prompts``. With 1, every prompt runs alone, as before.
    If the GPU runs out of memory, the batch is retried in smaller pieces.

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

    batch_size = max(1, batch_size)
    encoded = [tokenizer(p, add_special_tokens=False)["input_ids"] for p in prompts]
    order = sorted(range(len(prompts)), key=lambda i: len(encoded[i])) if batch_size > 1 else list(range(len(prompts)))

    def run(idx: list[int], n: int) -> dict[int, list[list[int]]]:
        """Sample ``n`` completions for each prompt in ``idx``; return trimmed ids per prompt.

        If the GPU runs out of memory, free it and retry in halves: first
        fewer prompts at once, then (for one long prompt) fewer completions
        at once. Samples are independent, so splitting does not change what
        is being measured.
        """
        try:
            return _generate_batch(model, encoded, idx, n, gen_kwargs, pad_id, eos, device)
        except torch.OutOfMemoryError:
            if len(idx) == 1 and n == 1:
                raise
            torch.cuda.empty_cache()
        if len(idx) > 1:
            half = len(idx) // 2
            return {**run(idx[:half], n), **run(idx[half:], n)}
        first = run(idx, n - n // 2)
        second = run(idx, n // 2)
        return {idx[0]: first[idx[0]] + second[idx[0]]}

    was_training = model.training
    model.eval()
    rollouts: list[Rollout | None] = [None] * len(prompts)
    try:
        with torch.no_grad(), _autocast(model, amp):
            for start in range(0, len(order), batch_size):
                idx = order[start : start + batch_size]
                for i, completions in run(idx, n_completions).items():
                    rollout = Rollout(prompt_ids=list(encoded[i]))
                    for ids in completions:
                        rollout.completion_ids.append(ids)
                        rollout.texts.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
                    rollouts[i] = rollout
    finally:
        if was_training:
            model.train()
    return rollouts


def _generate_batch(model, encoded, idx, n, gen_kwargs, pad_id, eos, device) -> dict[int, list[list[int]]]:
    """One ``model.generate`` call for the prompts ``idx`` (left-padded), ``n`` completions each."""
    width = max(len(encoded[i]) for i in idx)
    input_ids = torch.full((len(idx), width), pad_id, dtype=torch.long)
    attention = torch.zeros((len(idx), width), dtype=torch.long)
    for row, i in enumerate(idx):
        ids = encoded[i]
        input_ids[row, width - len(ids):] = torch.tensor(ids, dtype=torch.long)
        attention[row, width - len(ids):] = 1
    output_ids = model.generate(
        input_ids=input_ids.to(device), attention_mask=attention.to(device),
        **{**gen_kwargs, "num_return_sequences": n},
    )
    # generate returns n rows per prompt, prompt by prompt.
    return {
        i: [trim_completion(seq[width:].tolist(), eos, pad_id) for seq in output_ids[row * n : (row + 1) * n]]
        for row, i in enumerate(idx)
    }


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
