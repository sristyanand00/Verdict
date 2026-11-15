"""Batching and train/validation splits over BIRD tasks."""

import random
from collections.abc import Callable

from verdict.data.loaders import DIFFICULTIES, BirdTask


def batch_dataset(tasks: list[BirdTask], batch_size: int = 32) -> list[list[BirdTask]]:
    """Split tasks into consecutive batches of ``batch_size`` (the last may be shorter)."""
    return [tasks[i : i + batch_size] for i in range(0, len(tasks), batch_size)]


def batch_by_difficulty(tasks: list[BirdTask]) -> dict[str, list[BirdTask]]:
    """Group tasks by difficulty: ``{"simple": [...], "moderate": [...], "challenging": [...]}``."""
    groups: dict[str, list[BirdTask]] = {d: [] for d in DIFFICULTIES}
    for task in tasks:
        # BIRD train tasks are "unknown"; they get a group of their own.
        groups.setdefault(task.difficulty, []).append(task)
    return groups


def holdout_split(
    tasks: list[BirdTask],
    val_size: int,
    seed: int = 0,
    eligible: Callable[[BirdTask], bool] = lambda t: True,
) -> tuple[list[BirdTask], list[BirdTask]]:
    """Hold out ``val_size`` random tasks for validation; the rest train.

    Only tasks for which ``eligible`` is true can be held out (for example,
    tasks whose database exists, so their answers can be checked). The choice
    depends only on ``seed`` and the task ids, so SFT and GRPO runs that use
    the same seed hold out the same questions and never train on them.
    """
    candidates = sorted((t for t in tasks if eligible(t)), key=lambda t: t.question_id)
    val = random.Random(seed).sample(candidates, min(val_size, len(candidates)))
    held = {t.question_id for t in val}
    train = [t for t in tasks if t.question_id not in held]
    return train, sorted(val, key=lambda t: t.question_id)


def create_train_val_split(
    tasks: list[BirdTask], train_ratio: float = 0.8
) -> tuple[list[BirdTask], list[BirdTask]]:
    """Sequential split: the first ``train_ratio`` of tasks train, the rest validate.

    BIRD dev is ordered by database, so this keeps the last databases unseen
    during training.
    """
    split = int(len(tasks) * train_ratio)
    return tasks[:split], tasks[split:]


def stratified_train_val_split(
    tasks: list[BirdTask], train_ratio: float = 0.8
) -> tuple[list[BirdTask], list[BirdTask]]:
    """Sequential split applied within each difficulty, so both sides keep the same mix."""
    train, val = [], []
    for group in batch_by_difficulty(tasks).values():
        split = int(len(group) * train_ratio)
        train.extend(group[:split])
        val.extend(group[split:])
    return train, val
