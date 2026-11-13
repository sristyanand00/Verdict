"""GRPO helpers that need no torch: ordering, advantages, trimming."""

import pickle

import pytest

from tests.fixtures import make_tiny_db
from verdict.data.schema import get_schema
from verdict.train.grpo_utils import group_advantages, repeat_per_group, trim_completion
from verdict.train.reward import SQLRewardFunction


def test_repeat_per_group_keeps_each_prompt_with_its_completions():
    # Completions come back as [p0, p0, p0, p1, p1, p1]; `prompts * n` would
    # give [p0, p1, p0, p1, ...] and pair most completions with the wrong prompt.
    assert repeat_per_group(["p0", "p1"], 3) == ["p0", "p0", "p0", "p1", "p1", "p1"]
    assert repeat_per_group(["p0", "p1"], 3) != ["p0", "p1"] * 3


def test_group_advantages_are_relative_to_own_group():
    rewards = [1.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.1, 0.1]
    adv = group_advantages(rewards, 4)
    assert adv[:4] == pytest.approx([0.75, -0.25, -0.25, -0.25])
    assert adv[4:] == pytest.approx([0.0, 0.0, 0.0, 0.0])  # identical group: no signal


def test_group_advantages_scaled():
    adv = group_advantages([1.0, 0.0], 2, scale=True)
    assert adv == pytest.approx([1.0, -1.0], abs=1e-3)


def test_group_advantages_rejects_ragged_groups():
    with pytest.raises(ValueError):
        group_advantages([1.0, 0.0, 0.0], 2)


def test_trim_completion_keeps_first_eos_and_drops_padding():
    eos, pad = {9}, 0
    assert trim_completion([5, 6, 9, 0, 0], eos, pad) == [5, 6, 9]
    assert trim_completion([5, 6, 7], eos, pad) == [5, 6, 7]  # hit max_tokens
    assert trim_completion([5, 0, 0], eos, pad) == [5]
    # Qwen pads with a token that is also an EOS id.
    assert trim_completion([5, 9, 9, 9], eos, 9) == [5, 9]


def test_gold_result_is_cached(tmp_path, monkeypatch):
    make_tiny_db(tmp_path)
    fn = SQLRewardFunction(db_root=tmp_path, workers=1)
    gold = "SELECT name FROM students WHERE year = 2"
    out = fn(prompts=[], completions=[gold] * 4, gold_sql=[gold] * 4, db_id=["tiny"] * 4)
    assert out == [1.0] * 4
    assert len(fn._gold_cache) == 1
    # The cache does not travel to worker processes.
    assert pickle.loads(pickle.dumps(fn))._gold_cache == {}


def test_schema_without_sample_rows_does_not_claim_tables_are_empty(tmp_path):
    db = make_tiny_db(tmp_path)
    text = get_schema(db, num_samples=0)
    assert "CREATE TABLE students" in text
    assert "empty table" not in text and "Sample rows" not in text
