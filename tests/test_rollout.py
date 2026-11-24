"""Batched generation and re-scoring tests on a tiny random model (CPU, no download)."""

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("tokenizers")

from tests.fixtures import make_tiny_db  # noqa: E402
from tests.test_grpo import _tiny_model, _tiny_tokenizer  # noqa: E402
from verdict.data.loaders import BirdTask  # noqa: E402
from verdict.train.evaluation import OUTCOME, score_texts  # noqa: E402
from verdict.train.reward import SQLRewardFunction  # noqa: E402
from verdict.train.rollout import GenerationConfig, generate_ids  # noqa: E402

PROMPTS = [
    "Question Schema",
    "SELECT name FROM students WHERE year = 2 Question Schema Hint",
    "Hint",
    "SELECT name Question",
    "Schema Hint SELECT",
]


@pytest.fixture
def model_and_tok():
    tok = _tiny_tokenizer()
    model = _tiny_model(len(tok), tok.eos_token_id, tok.pad_token_id)
    model.eval()
    return model, tok


def test_batched_greedy_matches_one_at_a_time(model_and_tok):
    model, tok = model_and_tok
    config = GenerationConfig(temperature=0, max_tokens=6)
    single = generate_ids(model, tok, PROMPTS, n_completions=1, config=config, amp=False, batch_size=1)
    batched = generate_ids(model, tok, PROMPTS, n_completions=1, config=config, amp=False, batch_size=3)
    assert [r.prompt_ids for r in batched] == [r.prompt_ids for r in single]
    assert [r.completion_ids for r in batched] == [r.completion_ids for r in single]
    assert [r.texts for r in batched] == [r.texts for r in single]


def test_batched_sampling_keeps_prompt_order_and_group_size(model_and_tok):
    model, tok = model_and_tok
    config = GenerationConfig(temperature=0.9, max_tokens=4)
    rollouts = generate_ids(model, tok, PROMPTS, n_completions=3, config=config, amp=False, batch_size=2)
    assert len(rollouts) == len(PROMPTS)
    for prompt, r in zip(PROMPTS, rollouts):
        assert r.prompt_ids == tok(prompt, add_special_tokens=False)["input_ids"]
        assert len(r.completion_ids) == len(r.texts) == 3
        assert tok.pad_token_id not in r.completion_ids[0]


def test_score_texts_rescoring_saved_sql(tmp_path):
    db = make_tiny_db(tmp_path / "dbs")
    gold = "SELECT name FROM students WHERE year = 2"
    tasks = [
        BirdTask(question_id=i, db_id="tiny", question="q", evidence="", gold_sql=gold, difficulty="simple",
                 db_path=db)
        for i in range(3)
    ]
    texts = [gold, "SELECT name FROM students", "SELECT nope FROM students"]
    result = score_texts(texts, tasks, SQLRewardFunction(tmp_path / "dbs", timeout_s=30, workers=2))
    assert result.outcomes[0] == OUTCOME["correct"]
    assert result.outcomes[2] == OUTCOME["failed"]
    assert [r["sql"] for r in result.rows(tasks)] == texts


def test_out_of_memory_retries_in_smaller_pieces(model_and_tok, monkeypatch):
    """A batch too big for the GPU is split (prompts, then completions) instead of crashing."""
    import verdict.train.rollout as rollout_mod

    model, tok = model_and_tok
    real = rollout_mod._generate_batch
    calls = []

    def limited(model, encoded, idx, n, *rest):
        calls.append(len(idx) * n)
        if len(idx) * n > 2:
            raise torch.OutOfMemoryError("fake")
        return real(model, encoded, idx, n, *rest)

    monkeypatch.setattr(rollout_mod, "_generate_batch", limited)
    config = GenerationConfig(temperature=0.9, max_tokens=4)
    rollouts = generate_ids(model, tok, PROMPTS, n_completions=4, config=config, amp=False, batch_size=2)
    assert len(rollouts) == len(PROMPTS)
    for prompt, r in zip(PROMPTS, rollouts):
        assert r.prompt_ids == tok(prompt, add_special_tokens=False)["input_ids"]
        assert len(r.completion_ids) == len(r.texts) == 4
    assert max(c for c in calls if c <= 2) == 2
