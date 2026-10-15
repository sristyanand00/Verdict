"""Batch processing utilities for training pipeline.

    batch_tasks_by_db(tasks) -> dict[str, list[BirdTask]]
    batch_dataset(tasks, batch_size) -> list[list[BirdTask]]
"""

from typing import Iterator
from verdict.data.loaders import BirdTask


def batch_tasks_by_db(tasks: list[BirdTask]) -> dict[str, list[BirdTask]]:
    """Group tasks by database ID.
    
    Useful for efficient batch processing since tasks using the same database
    can share the connection and avoid redundant connection overhead.
    
    Args:
        tasks: List of BirdTask objects
    
    Returns:
        Dictionary mapping db_id -> list of tasks for that database
    """
    batches = {}
    for task in tasks:
        if task.db_id not in batches:
            batches[task.db_id] = []
        batches[task.db_id].append(task)
    return batches


def batch_dataset(
    tasks: list[BirdTask],
    batch_size: int = 32,
) -> list[list[BirdTask]]:
    """Split tasks into fixed-size batches.
    
    Args:
        tasks: List of BirdTask objects
        batch_size: Number of tasks per batch
    
    Returns:
        List of batches (each batch is a list of tasks)
    """
    batches = []
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i : i + batch_size]
        batches.append(batch)
    return batches


def batch_by_difficulty(tasks: list[BirdTask]) -> dict[str, list[BirdTask]]:
    """Group tasks by difficulty level.
    
    Args:
        tasks: List of BirdTask objects
    
    Returns:
        Dictionary mapping difficulty -> list of tasks
        e.g. {"simple": [...], "moderate": [...], "challenging": [...]}
    """
    batches = {"simple": [], "moderate": [], "challenging": []}
    for task in tasks:
        batches[task.difficulty].append(task)
    return batches


def balance_batches(
    tasks: list[BirdTask],
    batch_size: int = 32,
) -> list[list[BirdTask]]:
    """Create balanced batches with mixed difficulties.
    
    Useful for training to ensure model sees diverse difficulties in each batch.
    
    Args:
        tasks: List of BirdTask objects
        batch_size: Number of tasks per batch
    
    Returns:
        List of balanced batches
    """
    # Group by difficulty
    by_difficulty = batch_by_difficulty(tasks)
    
    # Create iterators for each difficulty
    iterators = {
        diff: iter(by_difficulty[diff])
        for diff in ["simple", "moderate", "challenging"]
    }
    
    batches = []
    current_batch = []
    
    # Round-robin through difficulties
    difficulties = ["simple", "moderate", "challenging"]
    diff_idx = 0
    
    while True:
        # Try to get from current difficulty
        try:
            task = next(iterators[difficulties[diff_idx]])
            current_batch.append(task)
            
            if len(current_batch) == batch_size:
                batches.append(current_batch)
                current_batch = []
        except StopIteration:
            # Move to next difficulty
            pass
        
        # Move to next difficulty for next iteration
        diff_idx = (diff_idx + 1) % len(difficulties)
        
        # Check if we're done
        all_exhausted = all(
            False  # All iterators exhausted is checked above
            for it in iterators.values()
        )
        if len(current_batch) == 0 and all(
            len(list(iterators[d])) == 0 for d in difficulties
        ):
            break
    
    # Add remaining tasks
    if current_batch:
        batches.append(current_batch)
    
    return batches


def create_train_val_split(
    tasks: list[BirdTask],
    train_ratio: float = 0.8,
) -> tuple[list[BirdTask], list[BirdTask]]:
    """Split tasks into train and validation sets.
    
    Args:
        tasks: List of BirdTask objects
        train_ratio: Fraction for training (rest goes to validation)
    
    Returns:
        Tuple of (train_tasks, val_tasks)
    """
    split_idx = int(len(tasks) * train_ratio)
    return tasks[:split_idx], tasks[split_idx:]


def stratified_train_val_split(
    tasks: list[BirdTask],
    train_ratio: float = 0.8,
) -> tuple[list[BirdTask], list[BirdTask]]:
    """Split tasks maintaining difficulty distribution.
    
    Args:
        tasks: List of BirdTask objects
        train_ratio: Fraction for training
    
    Returns:
        Tuple of (train_tasks, val_tasks) with similar difficulty distributions
    """
    # Group by difficulty
    by_difficulty = batch_by_difficulty(tasks)
    
    train_tasks = []
    val_tasks = []
    
    # Split each difficulty group
    for diff, diff_tasks in by_difficulty.items():
        split_idx = int(len(diff_tasks) * train_ratio)
        train_tasks.extend(diff_tasks[:split_idx])
        val_tasks.extend(diff_tasks[split_idx:])
    
    return train_tasks, val_tasks
