"""End-to-end GRPO trainer test on a tiny random model (CPU, no download).

Skipped when torch/transformers are not installed (CI installs neither).
"""

import json

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
tokenizers = pytest.importorskip("tokenizers")

from tests.fixtures import make_tiny_db  # noqa: E402
from verdict.data.loaders import BirdTask  # noqa: E402
from verdict.train import grpo as grpo_mod  # noqa: E402
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig  # noqa: E402


def _tiny_tokenizer():
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    tok = Tokenizer(models.BPE())
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=400, special_tokens=["<pad>", "<eos>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tok.train_from_iterator(["SELECT name FROM students WHERE year = 2", "Question Schema Hint"], trainer)
    return transformers.PreTrainedTokenizerFast(tokenizer_object=tok, pad_token="<pad>", eos_token="<eos>")


def _tiny_model(vocab_size, eos_id, pad_id):
    cfg = transformers.Qwen2Config(
        vocab_size=vocab_size, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=4096,
        eos_token_id=eos_id, pad_token_id=pad_id, tie_word_embeddings=True,
    )
    torch.manual_seed(0)
    return transformers.Qwen2ForCausalLM(cfg)


@pytest.fixture
def trainer(tmp_path, monkeypatch):
    make_tiny_db(tmp_path / "dbs")
    tok = _tiny_tokenizer()
    model = _tiny_model(len(tok), tok.eos_token_id, tok.pad_token_id)
    monkeypatch.setattr(GRPOTrainer, "_load_tokenizer", staticmethod(lambda source: tok))
    real_load = GRPOTrainer._load_model

    def load_model(self, source):
        # Run the real post-load steps (dtype, device, checkpointing) on the tiny model.
        monkeypatch.setattr(grpo_mod.AutoModelForCausalLM, "from_pretrained", lambda s: model)
        return real_load(self, source)

    monkeypatch.setattr(GRPOTrainer, "_load_model", load_model)
    cfg = GRPOTrainingConfig(
        model_name="tiny", num_epochs=1, batch_size=2, num_generations=3, max_tokens=8,
        micro_batch_size=2, learning_rate=1e-2, eval_max_tasks=2,
        checkpoint_dir=tmp_path / "ckpt", device="cpu", reward_workers=2,
    )
    return GRPOTrainer(cfg, db_root=tmp_path / "dbs")


def _task(qid):
    return BirdTask(
        question_id=qid, db_id="tiny", question="Names of year 2 students?", evidence="year = 2",
        gold_sql="SELECT name FROM students WHERE year = 2", difficulty="simple", db_path=None,
    )


def test_prompt_contains_schema_question_and_hint(trainer):
    text = trainer.prompt_for(_task(1))
    assert "CREATE TABLE students" in text
    assert "Names of year 2 students?" in text
    assert "year = 2" in text


def test_db_root_must_be_the_databases_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match="dev_databases"):
        GRPOTrainer(GRPOTrainingConfig(device="cpu"), db_root=tmp_path / "missing")


def test_logprobs_match_a_plain_forward_pass(trainer):
    """The hidden-state shortcut must give the same log-probs as full logits."""
    p, c = [5, 6, 7, 8], [9, 10, 11]
    got = trainer._sequence_logprobs([(p, c, 1.0), ([5, 6], [7], 1.0)])
    with torch.no_grad():
        logits = trainer.model(torch.tensor([p + c])).logits[0]
    expected = torch.log_softmax(logits.float(), -1)[torch.arange(3, 6), torch.tensor(c)].sum()
    assert got[0].item() == pytest.approx(expected.item(), rel=1e-4)


def test_update_makes_rewarded_completion_more_likely(trainer):
    """Sign check: positive advantage must raise log p, negative must lower it."""
    p, good, bad = [5, 6, 7], [8, 9, 10], [11, 12, 13]
    with torch.no_grad():
        before = trainer._sequence_logprobs([(p, good, 0), (p, bad, 0)])
    for _ in range(3):
        trainer._accumulate_gradients([(p, good, 1.0), (p, bad, -1.0)])
        trainer._optimizer_step()
    with torch.no_grad():
        after = trainer._sequence_logprobs([(p, good, 0), (p, bad, 0)])
    assert after[0] > before[0]
    assert after[1] < before[1]


class _SpreadReward:
    """A random tiny model never writes valid SQL, so every reward would be 0
    and there would be no gradient. This gives one 'correct' per group of 3."""

    rewards = {"correct": 1.0, "wrong": 0.1, "failed": 0.0}

    def __call__(self, prompts, completions, **kwargs):
        return [1.0 if i % 3 == 0 else 0.0 for i in range(len(completions))]


def test_fit_updates_weights_and_saves_checkpoints(trainer):
    trainer.reward_fn = _SpreadReward()
    before = [p.detach().clone() for p in trainer.model.parameters()]
    result = trainer.fit([_task(1), _task(2), _task(3)], val_tasks=[_task(4)])
    after = list(trainer.model.parameters())

    assert any(not torch.equal(a, b) for a, b in zip(before, after)), "no weights changed"
    assert all(torch.isfinite(p).all() for p in after)
    assert trainer.global_step >= 1
    assert len(result["metrics"]["val_accuracy"]) == 1
    latest = trainer.checkpoint_dir / "latest"
    assert (latest / "config.json").exists()
    assert json.loads((latest / "training_state.json").read_text())["epoch"] == 1
    assert (trainer.checkpoint_dir / "best").is_dir()
