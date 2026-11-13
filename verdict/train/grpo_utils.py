"""Pure-Python helpers for the GRPO loop.

Kept free of torch so CI can test them without installing a GPU stack. The
ordering rule they all share: completions are grouped per prompt, so a batch
of prompts [p0, p1] with n=3 gives completions [p0, p0, p0, p1, p1, p1].
"""

import statistics
from collections.abc import Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")


def repeat_per_group(items: Sequence[T], n: int) -> list[T]:
    """Repeat each item ``n`` times in place: [a, b] -> [a, a, b, b] for n=2.

    This matches the order completions come back in. Note that ``items * n``
    gives [a, b, a, b], which pairs completions with the wrong prompt.
    """
    return [item for item in items for _ in range(n)]


def group_advantages(rewards: Sequence[float], n: int, scale: bool = False, eps: float = 1e-4) -> list[float]:
    """GRPO advantage: each reward minus its group's mean.

    ``rewards`` holds consecutive groups of ``n``. With ``scale`` the result is
    also divided by the group's standard deviation (the original GRPO paper).
    It is off by default, following Dr. GRPO (arXiv:2503.20783), which shows the
    division over-weights groups whose rewards are nearly all the same.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if len(rewards) % n:
        raise ValueError(f"{len(rewards)} rewards do not split into groups of {n}")
    out: list[float] = []
    for i in range(0, len(rewards), n):
        group = rewards[i : i + n]
        mean = statistics.fmean(group)
        std = statistics.pstdev(group) if scale else 1.0
        out.extend((r - mean) / (std + eps) if scale else r - mean for r in group)
    return out


def trim_completion(ids: Sequence[int], eos_ids: Iterable[int], pad_id: int | None) -> list[int]:
    """Cut generated token ids at the first end-of-sequence token, keeping it.

    ``model.generate`` pads finished sequences up to the longest one. Those
    pads must not be trained on. The EOS token itself is kept so the model is
    rewarded (or penalised) for stopping where it did.
    """
    eos = set(eos_ids)
    out: list[int] = []
    for tok in ids:
        out.append(tok)
        if tok in eos:
            return out
    # No EOS: the completion hit max_tokens. Drop trailing pads, if any.
    while out and pad_id is not None and out[-1] == pad_id:
        out.pop()
    return out
