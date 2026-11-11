from pathlib import Path

from verdict.data.loaders import BirdTask
from verdict.train.batch import batch_by_difficulty, batch_dataset, stratified_train_val_split

DIFFS = ["simple"] * 10 + ["moderate"] * 5 + ["challenging"] * 5
TASKS = [BirdTask(i, "db", "q", "", "SELECT 1", d, Path("x")) for i, d in enumerate(DIFFS)]


def test_batch_dataset_keeps_every_task():
    batches = batch_dataset(TASKS, batch_size=8)
    assert [len(b) for b in batches] == [8, 8, 4]


def test_batch_by_difficulty():
    groups = batch_by_difficulty(TASKS)
    assert {k: len(v) for k, v in groups.items()} == {"simple": 10, "moderate": 5, "challenging": 5}


def test_stratified_split_keeps_the_mix_and_loses_nothing():
    train, val = stratified_train_val_split(TASKS, 0.8)
    assert len(train) == 16 and len(val) == 4
    assert {t.question_id for t in train} | {t.question_id for t in val} == set(range(20))
    assert sum(t.difficulty == "simple" for t in val) == 2
