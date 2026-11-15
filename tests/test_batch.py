from pathlib import Path

from verdict.data.loaders import BirdTask
from verdict.train.batch import batch_by_difficulty, batch_dataset, holdout_split, stratified_train_val_split

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


def test_unknown_difficulty_gets_its_own_group():
    tasks = TASKS + [BirdTask(99, "db", "q", "", "SELECT 1", "unknown", Path("x"))]
    assert len(batch_by_difficulty(tasks)["unknown"]) == 1


def test_holdout_split_is_repeatable_and_respects_eligibility():
    eligible = lambda t: t.question_id % 2 == 0  # noqa: E731
    train, val = holdout_split(TASKS, 3, seed=5, eligible=eligible)
    again_train, again_val = holdout_split(list(reversed(TASKS)), 3, seed=5, eligible=eligible)
    assert [t.question_id for t in val] == [t.question_id for t in again_val]
    assert len(val) == 3 and all(t.question_id % 2 == 0 for t in val)
    assert {t.question_id for t in train}.isdisjoint(t.question_id for t in val)
    assert len(train) + len(val) == len(TASKS)
