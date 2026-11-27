"""Question selection and input lookup used to continue a GRPO run."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("torch")


def _load(name: str):
    path = Path(__file__).resolve().parent.parent / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_second_run_questions_do_not_repeat_the_first():
    train_grpo = _load("train_grpo")
    tasks = list(range(9228))
    first = train_grpo.evenly_spaced(tasks, 500)
    rest = [t for t in tasks if t not in set(first)]
    second = train_grpo.evenly_spaced(rest, 1100)
    assert (len(first), len(second)) == (500, 1100)
    assert not set(first) & set(second)
    assert train_grpo.evenly_spaced(tasks[:3], 10) == tasks[:3]


def test_previous_adapter_is_found_at_any_depth(tmp_path):
    kaggle = _load("kaggle_grpo")
    assert kaggle.previous_adapter(str(tmp_path)) is None
    best = tmp_path / "notebooks" / "someone" / "run" / "grpo_v1" / "best"
    best.mkdir(parents=True)
    (best / "adapter_config.json").write_text("{}")
    assert kaggle.previous_adapter(str(tmp_path)) == best
