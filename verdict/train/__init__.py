"""GRPO training: reward, rollout, trainer loop, control domain."""

from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.train.reward import SQLRewardFunction
from verdict.train.rollout import generate, GenerationConfig
from verdict.train.batch import (
    batch_dataset,
    batch_tasks_by_db,
    batch_by_difficulty,
    create_train_val_split,
    stratified_train_val_split,
)
from verdict.train.monitor import TrainingMonitor

__all__ = [
    "GRPOTrainer",
    "GRPOTrainingConfig",
    "SQLRewardFunction",
    "generate",
    "GenerationConfig",
    "batch_dataset",
    "batch_tasks_by_db",
    "batch_by_difficulty",
    "create_train_val_split",
    "stratified_train_val_split",
    "TrainingMonitor",
]
