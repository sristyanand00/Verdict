"""Batching and train/validation splits over BIRD tasks."""

from verdict.data.loaders import DIFFICULTIES, BirdTask


def batch_dataset(tasks: list[BirdTask], batch_size: int = 32) -> list[list[BirdTask]]:
    """Split tasks into consecutive batches of ``batch_size`` (the last may be shorter)."""
    return [tasks[i : i + batch_size] for i in range(0, len(tasks), batch_size)]


def batch_by_difficulty(tasks: list[BirdTask]) -> dict[str, list[BirdTask]]:
    """Group tasks by difficulty: ``{"simple": [...], "moderate": [...], "challenging": [...]}``."""
    groups: dict[str, list[BirdTask]] = {d: [] for d in DIFFICULTIES}
    for task in tasks:
        groups[task.difficulty].append(task)
    return groups


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
