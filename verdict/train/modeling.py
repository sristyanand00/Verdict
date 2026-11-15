"""Model setup shared by SFT, GRPO and evaluation.

    prepare_for_training(model, device, lora=LoraSettings(r=16))   -> trainable model
    load_for_inference("checkpoints/best", device)                 -> (model, tokenizer)
    completion_token_logprobs(model, pairs, pad_id, device, ctx)   -> per-token log p

Two ways to train:

* Full fine-tuning (``lora.r == 0``): every weight is trained, in float32.
  Fits a 0.5B model on a 16 GB T4, not a 1.5B one: weights, gradients and
  two AdamW states need about 16 bytes per parameter.
* LoRA (``lora.r > 0``): the original weights are frozen and small low-rank
  matrices are added to the attention and MLP projections (Hu et al., 2021).
  On CUDA the frozen weights are kept in float16 (half the memory); the LoRA
  weights are float32 so that small AdamW updates are not rounded away.
  A checkpoint then holds only the LoRA weights (tens of MB, not GB).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

#: Qwen2 / Llama-style projection names.
LORA_TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


@dataclass
class LoraSettings:
    r: int = 0  # 0 means full fine-tuning
    alpha: int = 32
    dropout: float = 0.05
    target_modules: tuple[str, ...] = LORA_TARGETS


def is_adapter_dir(path: str | Path) -> bool:
    """True if ``path`` holds a LoRA adapter rather than a full model."""
    return (Path(path) / "adapter_config.json").exists()


def adapter_base_model(path: str | Path) -> str:
    """The base model a LoRA adapter was trained on."""
    data = json.loads((Path(path) / "adapter_config.json").read_text(encoding="utf-8"))
    return data["base_model_name_or_path"]


def load_tokenizer(source: str | Path):
    tokenizer = AutoTokenizer.from_pretrained(source)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def _enable_checkpointing(model) -> None:
    # Renamed in newer transformers; Kaggle images may have either.
    if hasattr(model, "activation_checkpointing_enable"):
        model.activation_checkpointing_enable(activation_checkpointing_kwargs={"use_reentrant": False})
    else:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False


def prepare_for_training(
    model,
    device: torch.device,
    lora: LoraSettings | None = None,
    adapter_path: str | Path | None = None,
    gradient_checkpointing: bool = True,
):
    """Move ``model`` to ``device`` and make it trainable.

    With ``lora.r > 0`` a new LoRA adapter is added. With ``adapter_path`` an
    existing adapter is loaded and kept trainable (to continue SFT, or to
    start GRPO from the SFT result). Otherwise all weights are trained.
    """
    lora = lora or LoraSettings()
    use_lora = lora.r > 0 or adapter_path is not None

    if not use_lora:
        model.to(device=device, dtype=torch.float32)
        if gradient_checkpointing:
            _enable_checkpointing(model)
        model.train()
        return model

    from peft import LoraConfig, PeftModel, get_peft_model

    base_dtype = torch.float16 if device.type == "cuda" else torch.float32
    model.to(device=device, dtype=base_dtype)
    for p in model.parameters():
        p.requires_grad_(False)
    if gradient_checkpointing:
        _enable_checkpointing(model)

    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=True)
    else:
        model = get_peft_model(
            model,
            LoraConfig(
                r=lora.r,
                lora_alpha=lora.alpha,
                lora_dropout=lora.dropout,
                target_modules=list(lora.target_modules),
                task_type="CAUSAL_LM",
            ),
        )
    for p in model.parameters():
        if p.requires_grad:
            p.data = p.data.float()
    model.train()
    return model


def trainable_parameters(model) -> list[torch.nn.Parameter]:
    return [p for p in model.parameters() if p.requires_grad]


def count_parameters(model) -> tuple[int, int]:
    """(trainable, total) parameter counts."""
    total = sum(p.numel() for p in model.parameters())
    return sum(p.numel() for p in trainable_parameters(model)), total


def load_for_training(source: str | Path, device: torch.device, lora: LoraSettings,
                      gradient_checkpointing: bool = True):
    """Load a base model name, a full checkpoint, or a LoRA adapter folder for training."""
    if is_adapter_dir(source):
        base = AutoModelForCausalLM.from_pretrained(adapter_base_model(source))
        return prepare_for_training(base, device, lora, adapter_path=source,
                                    gradient_checkpointing=gradient_checkpointing)
    model = AutoModelForCausalLM.from_pretrained(source)
    return prepare_for_training(model, device, lora, gradient_checkpointing=gradient_checkpointing)


def load_for_inference(source: str | Path, device: torch.device | str = "cuda"):
    """Load any model for evaluation: a Hugging Face name, a full checkpoint,
    or a LoRA adapter folder (merged into its base model).

    Returns ``(model, tokenizer)`` in float32, eval mode.
    """
    device = torch.device(device)
    if Path(source).is_dir() and is_adapter_dir(source):
        from peft import PeftModel

        base_name = adapter_base_model(source)
        base = AutoModelForCausalLM.from_pretrained(base_name)
        model = PeftModel.from_pretrained(base, str(source)).merge_and_unload()
        tok_source = source if (Path(source) / "tokenizer_config.json").exists() else base_name
    else:
        model = AutoModelForCausalLM.from_pretrained(source)
        tok_source = source
    model.to(device=device, dtype=torch.float32)
    model.eval()
    return model, load_tokenizer(tok_source)


def completion_token_logprobs(
    model,
    pairs: Sequence[tuple[Sequence[int], Sequence[int]]],
    pad_id: int,
    device: torch.device,
    autocast,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Log-probability of every completion token given its prompt.

    ``pairs`` is a list of ``(prompt_ids, completion_ids)``. Returns
    ``(token_logp, rows)``: one entry per completion token, and the index of
    the pair each token belongs to.

    The language-model head is applied only at completion positions. Full
    logits for a ~1500-token prompt with Qwen's 151k vocabulary would take
    gigabytes per sequence.
    """
    seqs = [list(p) + list(c) for p, c in pairs]
    width = max(len(s) for s in seqs)
    input_ids = torch.full((len(seqs), width), pad_id, dtype=torch.long)
    attention = torch.zeros((len(seqs), width), dtype=torch.long)
    rows, cols, targets = [], [], []
    for j, (p, c) in enumerate(pairs):
        input_ids[j, : len(p) + len(c)] = torch.tensor(seqs[j])
        attention[j, : len(p) + len(c)] = 1
        # The hidden state at position k predicts token k + 1.
        rows.extend([j] * len(c))
        cols.extend(range(len(p) - 1, len(p) - 1 + len(c)))
        targets.extend(c)
    input_ids, attention = input_ids.to(device), attention.to(device)
    rows_t = torch.tensor(rows, device=device, dtype=torch.long)
    cols_t = torch.tensor(cols, device=device, dtype=torch.long)
    targets_t = torch.tensor(targets, device=device, dtype=torch.long)

    with autocast:
        hidden = model.get_decoder()(
            input_ids=input_ids, attention_mask=attention, use_cache=False
        ).last_hidden_state
        logits = model.get_output_embeddings()(hidden[rows_t, cols_t])
    token_logp = torch.log_softmax(logits.float(), dim=-1).gather(1, targets_t[:, None]).squeeze(1)
    return token_logp, rows_t
